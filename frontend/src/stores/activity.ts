// Local activity log for the progress dashboard.
// Stored only in this browser (localStorage), same as the rest of the
// no-account design: no message text, just dates, features and minutes.
import { defineStore } from 'pinia'
import { dateKey, type ActivityEvent, type Feature } from '@/utils/progress'

const KEY = 'bw-activity-v1'
const MAX_EVENTS = 2000 // plenty for a year of use, keeps storage small

interface Saved {
  openDays: string[]
  events: ActivityEvent[]
  viewed: string[] // phrase ids opened with "See what this means"
  reviews: Record<string, string[]> // phrase id -> dates reviewed in Study
}

function load(): Saved {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const s = JSON.parse(raw) as Partial<Saved>
      return { openDays: s.openDays ?? [], events: s.events ?? [], viewed: s.viewed ?? [], reviews: s.reviews ?? {} }
    }
  } catch {
    // private window or blocked storage: start empty, the page still works
  }
  return { openDays: [], events: [], viewed: [], reviews: {} }
}

export const useActivityStore = defineStore('activity', {
  state: (): Saved => load(),

  actions: {
    persist() {
      try {
        localStorage.setItem(KEY, JSON.stringify({ openDays: this.openDays, events: this.events, viewed: this.viewed, reviews: this.reviews }))
      } catch {
        /* storage full or blocked, nothing else to do */
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

    clearAll() {
      this.openDays = []
      this.events = []
      this.viewed = []
      this.reviews = {}
      this.persist()
    },
  },
})
