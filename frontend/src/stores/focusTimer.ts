// The focus timer's session. Kept here rather than in the timer component, so
// going to another page to do the task and coming back doesn't lose it.
// sessionStorage covers a reload too; closing the tab ends the session.
//
// Time is worked out from timestamps (startedAt), never counted up in place,
// so it stays right while the page isn't showing.
import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { Feature } from '@/utils/progress'

const KEY = 'bw-focus-timer'

export type TimerNotice = null | 'timeUp' | 'hyperfocus' | 'saved'

interface Session {
  lengthMin: number // 0 = open, counts up
  feature: Feature
  intent: string
  running: boolean
  startedAt: number // Date.now() minus the time already done, while running
  elapsed: number // seconds, kept while paused
  nudgedAt: number // minutes, for the 45-minute check-in in open mode
  notice: TimerNotice
  savedMinutes: number
}

const fresh = (): Session => ({
  lengthMin: 10, feature: 'decoder', intent: '', running: false, startedAt: 0, elapsed: 0, nudgedAt: 0, notice: null, savedMinutes: 0,
})

function load(): Session {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (raw) return { ...fresh(), ...(JSON.parse(raw) as Partial<Session>) }
  } catch {
    // blocked storage: start fresh, the timer still works on this page
  }
  return fresh()
}

export const useFocusTimerStore = defineStore('focusTimer', () => {
  const s = load()
  const lengthMin = ref(s.lengthMin)
  const feature = ref<Feature>(s.feature)
  const intent = ref(s.intent)
  const running = ref(s.running)
  const startedAt = ref(s.startedAt)
  const elapsed = ref(s.running ? (Date.now() - s.startedAt) / 1000 : s.elapsed)
  const nudgedAt = ref(s.nudgedAt)
  const notice = ref<TimerNotice>(s.notice)
  const savedMinutes = ref(s.savedMinutes)

  // While running, elapsed changes four times a second but follows from
  // startedAt, so it isn't written out until the timer stops.
  const session = computed<Session>(() => ({
    lengthMin: lengthMin.value, feature: feature.value, intent: intent.value, running: running.value, startedAt: startedAt.value,
    elapsed: running.value ? 0 : elapsed.value, nudgedAt: nudgedAt.value, notice: notice.value, savedMinutes: savedMinutes.value,
  }))
  watch(session, (v) => {
    try { sessionStorage.setItem(KEY, JSON.stringify(v)) } catch { /* the session just won't survive a reload */ }
  })

  // Sign-out and Settings' delete: what someone was working on doesn't stay behind.
  function reset() {
    const f = fresh()
    lengthMin.value = f.lengthMin
    feature.value = f.feature
    intent.value = f.intent
    running.value = f.running
    startedAt.value = f.startedAt
    elapsed.value = f.elapsed
    nudgedAt.value = f.nudgedAt
    notice.value = f.notice
    savedMinutes.value = f.savedMinutes
    try { sessionStorage.removeItem(KEY) } catch { /* ignore */ }
  }

  return { lengthMin, feature, intent, running, startedAt, elapsed, nudgedAt, notice, savedMinutes, reset }
})
