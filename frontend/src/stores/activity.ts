// Activity log for the progress dashboard.
//
// Kept in this browser (localStorage) first, always: no message text, just
// dates, features and minutes. When someone is signed in, the same data is
// copied to their account (services/progressSyncService.ts) so their days and
// badges follow them to another device. The browser stays the source of truth,
// so a failed sync never costs anyone anything.
//
// The one thing that never syncs is the focus timer's "what are you working
// on?" text. It's free text, so it stays here.
import { defineStore } from 'pinia'
import { dateKey, type ActivityEvent, type Feature } from '@/utils/progress'
import { useAccountStore } from '@/stores/account'
import { useCardsStore } from '@/stores/cards'
import { useFocusTimerStore } from '@/stores/focusTimer'
import {
  clearProgress,
  pushProgress,
  type ProgressSnapshot,
  type ProgressUpload,
} from '@/services/progressSyncService'

const KEY = 'bw-activity-v1'
const MAX_EVENTS = 2000 // plenty for a year of use, keeps storage small
const SYNC_DELAY_MS = 4000 // a burst of clicks becomes one request

// Display flags the dashboard and timer keep on their own. Listed here so
// Settings' "delete" can clear them along with everything else.
const FLAG_KEYS = ['bw-progress-large', 'bw-progress-nobadges', 'bw-timer-hide-digits']
const SESSION_FLAG_KEYS = ['bw-refresher-later']

interface Saved {
  openDays: string[]
  events: ActivityEvent[]
  viewed: string[] // phrase ids opened with "See what this means"
  viewedOn: Record<string, string> // phrase id -> first day it was viewed (for syncing)
  reviews: Record<string, string[]> // phrase id -> dates reviewed in Study
  deviceId: string // random, made by this browser; says nothing about the person
  remoteEvents: ActivityEvent[] // minutes logged on the account's OTHER devices, no intent
}

function newDeviceId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `d${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`
}

function empty(): Saved {
  return { openDays: [], events: [], viewed: [], viewedOn: {}, reviews: {}, deviceId: newDeviceId(), remoteEvents: [] }
}

function load(): Saved {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const s = JSON.parse(raw) as Partial<Saved>
      const base = empty()
      return {
        openDays: s.openDays ?? [],
        events: s.events ?? [],
        viewed: s.viewed ?? [],
        viewedOn: s.viewedOn ?? {},
        reviews: s.reviews ?? {},
        deviceId: s.deviceId || base.deviceId,
        remoteEvents: s.remoteEvents ?? [],
      }
    }
  } catch {
    // private window or blocked storage: start empty, the page still works
  }
  return empty()
}

// ---------------------------------------------------------------- sync helpers (pure, so they're testable)

/**
 * What this device sends. Minutes are added up per day and feature (the
 * server keeps one number per device per day per feature), opened days become
 * "opened" rows, and views/reviews become dated events. `skip` holds review
 * keys that are local card ids rather than library pattern ids - those mean
 * nothing on another device, so they stay here.
 */
export function buildUpload(s: Saved, today: string, skip: Set<string> = new Set()): ProgressUpload {
  const minutes = new Map<string, number>()
  for (const e of s.events) {
    const k = `${e.date}|${e.feature}`
    minutes.set(k, (minutes.get(k) ?? 0) + e.minutes)
  }
  const activity: ProgressUpload['activity'] = [
    ...[...new Set(s.openDays)].map((date) => ({ date, feature: 'opened' as const, minutes: 0 })),
    ...[...minutes].map(([k, m]) => {
      const [date = '', feature = 'decoder'] = k.split('|')
      return { date, feature: feature as Feature, minutes: Math.min(m, 1440) }
    }),
  ]
  const phrase_events: ProgressUpload['phrase_events'] = [
    ...s.viewed.map((id) => ({ pattern_id: id, kind: 'viewed' as const, date: s.viewedOn[id] ?? today })),
    ...Object.entries(s.reviews)
      .filter(([id]) => !skip.has(id))
      .flatMap(([id, days]) => days.map((date) => ({ pattern_id: id, kind: 'reviewed' as const, date }))),
  ].filter((e) => e.pattern_id.length <= 40)
  return { device_id: s.deviceId, activity, phrase_events }
}

/**
 * Fold the account's whole set back into this browser. Everything is a
 * union - nothing here can remove a day or a review this device already has.
 * Minutes from other devices are kept apart from this device's own sessions,
 * so the two are added up on the dashboard and never double counted.
 */
export function mergeSnapshot(s: Saved, snap: ProgressSnapshot): void {
  const days = new Set(s.openDays)
  const remote: ActivityEvent[] = []
  for (const row of snap.activity) {
    if (row.feature === 'opened') days.add(row.date)
    else if (row.device_id !== s.deviceId && row.minutes > 0) {
      remote.push({ date: row.date, feature: row.feature, minutes: row.minutes })
    }
  }
  s.openDays = [...days].sort()
  s.remoteEvents = remote

  const viewed = new Set(s.viewed)
  for (const e of snap.phrase_events) {
    if (e.kind === 'viewed') {
      viewed.add(e.pattern_id)
      if (!s.viewedOn[e.pattern_id] || e.date < s.viewedOn[e.pattern_id]!) s.viewedOn[e.pattern_id] = e.date
    } else {
      const have = s.reviews[e.pattern_id] ?? []
      if (!have.includes(e.date)) s.reviews[e.pattern_id] = [...have, e.date].sort()
    }
  }
  s.viewed = [...viewed]
}

// ---------------------------------------------------------------- store

let syncTimer: ReturnType<typeof setTimeout> | null = null
let syncing = false
let again = false
// "Delete everything" has to win over a sync that is already on the wire.
// clearAll() bumps the epoch, and a sync that started before it throws its
// reply away (it holds the account's data from before the delete). The
// DELETE waits for that PUT to finish, so the server can't apply the PUT
// after it, and the next sync waits for the DELETE.
let epoch = 0
let inflight: Promise<unknown> | null = null
let clearing: Promise<void> | null = null

export const useActivityStore = defineStore('activity', {
  state: (): Saved => load(),

  getters: {
    // this device's sessions plus minutes from the account's other devices
    allEvents(state): ActivityEvent[] {
      return [...state.events, ...state.remoteEvents]
    },
  },

  actions: {
    persist() {
      try {
        localStorage.setItem(KEY, JSON.stringify(this.snapshot()))
      } catch {
        /* storage full or blocked, nothing else to do */
      }
      this.scheduleSync()
    },

    snapshot(): Saved {
      return {
        openDays: this.openDays, events: this.events, viewed: this.viewed, viewedOn: this.viewedOn,
        reviews: this.reviews, deviceId: this.deviceId, remoteEvents: this.remoteEvents,
      }
    },

    // call once when the app loads, counts towards badges
    markOpenedToday() {
      const today = dateKey()
      if (!this.openDays.includes(today)) {
        this.openDays.push(today)
        this.persist()
      }
    },

    // a finished focus-timer session, or time spent in a feature
    logSession(feature: Feature, minutes: number, intent?: string) {
      if (minutes <= 0) return
      const e: ActivityEvent = { date: dateKey(), feature, minutes: Math.round(minutes) }
      if (intent?.trim()) e.intent = intent.trim().slice(0, 120)
      this.events.push(e)
      if (this.events.length > MAX_EVENTS) this.events.splice(0, this.events.length - MAX_EVENTS)
      this.markOpenedToday()
      this.persist()
    },

    // Library: the user opened "See what this means" on a phrase
    markViewed(phraseId: string) {
      if (!this.viewed.includes(phraseId)) {
        this.viewed.push(phraseId)
        this.viewedOn[phraseId] = dateKey()
        this.persist()
      }
    },

    // Study: the user went through these cards today (once per card per day)
    markReviewed(phraseIds: string[]) {
      const today = dateKey()
      for (const id of phraseIds) {
        const days = this.reviews[id] ?? []
        if (!days.includes(today)) this.reviews[id] = [...days, today]
      }
      this.persist()
    },

    // A change made while signed in reaches the account a few seconds later.
    scheduleSync() {
      if (!useAccountStore().signedIn) return
      if (syncTimer) clearTimeout(syncTimer)
      syncTimer = setTimeout(() => {
        syncTimer = null
        void this.syncWithAccount()
      }, SYNC_DELAY_MS)
    },

    /**
     * Called when an account signs in (AppShell), and after changes while
     * signed in. Sends everything this device has, then folds the account's
     * whole set back in. Safe to call any number of times.
     */
    async syncWithAccount() {
      if (!useAccountStore().signedIn) return
      if (syncing) {
        again = true
        return
      }
      syncing = true
      try {
        while (clearing) await clearing
        const started = epoch
        // Review keys for cards saved from a decode are local card ids, not
        // library patterns. They stay on this device, like the cards do.
        const localOnly = new Set(useCardsStore().cards.filter((c) => !c.patternId).map((c) => c.id))
        const today = dateKey()
        // pin today's date on any older view that never had one, so the same
        // view isn't sent again with a new date tomorrow
        for (const id of this.viewed) if (!this.viewedOn[id]) this.viewedOn[id] = today

        const request = pushProgress(buildUpload(this.snapshot(), today, localOnly))
        inflight = request
        const snap = await request
        if (!snap || started !== epoch) return
        const s = this.snapshot()
        mergeSnapshot(s, snap)
        this.$patch({ openDays: s.openDays, remoteEvents: s.remoteEvents, viewed: s.viewed, viewedOn: s.viewedOn, reviews: s.reviews })
        try {
          localStorage.setItem(KEY, JSON.stringify(this.snapshot()))
        } catch {
          /* ignore */
        }
      } finally {
        syncing = false
        inflight = null
        if (again) {
          again = false
          void this.syncWithAccount()
        }
      }
    },

    // Settings' "delete": everything the dashboard keeps, here and (if signed
    // in) on the account, so it doesn't sync straight back down. Sign-out
    // calls it too, once signed out, so only this browser's copy goes.
    clearAll() {
      epoch++
      again = false
      this.openDays = []
      this.events = []
      this.viewed = []
      this.viewedOn = {}
      this.reviews = {}
      this.remoteEvents = []
      for (const k of FLAG_KEYS) {
        try { localStorage.removeItem(k) } catch { /* ignore */ }
      }
      for (const k of SESSION_FLAG_KEYS) {
        try { sessionStorage.removeItem(k) } catch { /* ignore */ }
      }
      // a session in progress goes too, with what they typed for it
      useFocusTimerStore().reset()
      if (syncTimer) {
        clearTimeout(syncTimer)
        syncTimer = null
      }
      try {
        localStorage.setItem(KEY, JSON.stringify(this.snapshot()))
      } catch {
        /* ignore */
      }
      if (useAccountStore().signedIn) {
        const done = (inflight ?? Promise.resolve()).then(() => clearProgress())
        clearing = done
        void done.finally(() => {
          if (clearing === done) clearing = null
        })
      }
    },
  },
})
