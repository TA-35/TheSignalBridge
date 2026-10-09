<script setup lang="ts">
// Focus timer for the progress page.
// Built for time blindness: short lengths, a ring you can read at a glance,
// an open count-up mode, no alarm at the end, and partial sessions still count.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { FEATURES, type Feature } from '@/utils/progress'
import { useActivityStore } from '@/stores/activity'

const props = defineProps<{ preset?: { minutes: number; feature: Feature; intent: string; nonce: number } }>()

const activity = useActivityStore()
const LENGTHS = [5, 10, 15, 25] as const
const HYPERFOCUS_MIN = 45
const CIRC = 2 * Math.PI * 56

const lengthMin = ref<number>(10) // 0 = open, counts up
const feature = ref<Feature>('decoder')
const intent = ref('')
const elapsed = ref(0) // seconds
const running = ref(false)
const notice = ref<null | 'timeUp' | 'hyperfocus' | 'saved'>(null)
const savedMinutes = ref(0)
const hideDigits = ref(readFlag('bw-timer-hide-digits'))

let startedAt = 0
let tick: number | undefined
let nudgedAt = 0

const FEATURE_LABEL: Record<Feature, string> = { decoder: 'Decoder', compose: 'Compose', study: 'Study', library: 'Library' }

function readFlag(k: string) {
  try { return localStorage.getItem(k) === '1' } catch { return false }
}
watch(hideDigits, (v) => { try { localStorage.setItem('bw-timer-hide-digits', v ? '1' : '0') } catch { /* ignore */ } })

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
const display = computed(() => (lengthMin.value ? fmt(Math.max(0, lengthMin.value * 60 - elapsed.value)) : fmt(elapsed.value)))
// countdown: ring empties as time runs out. Open mode: ring fills slowly over an hour
const dashOffset = computed(() => {
  if (!lengthMin.value) return CIRC * (1 - Math.min(1, elapsed.value / 3600))
  return CIRC * (1 - Math.max(0, lengthMin.value * 60 - elapsed.value) / (lengthMin.value * 60))
})

function setLength(m: number) {
  if (running.value || elapsed.value) return
  lengthMin.value = m
}

function start() {
  notice.value = null
  // based on timestamps so it stays right when the tab is in the background
  startedAt = Date.now() - elapsed.value * 1000
  running.value = true
  tick = window.setInterval(() => {
    elapsed.value = (Date.now() - startedAt) / 1000
    if (lengthMin.value && elapsed.value >= lengthMin.value * 60) timeUp()
    if (!lengthMin.value && elapsed.value / 60 >= nudgedAt + HYPERFOCUS_MIN) {
      nudgedAt += HYPERFOCUS_MIN
      notice.value = 'hyperfocus'
    }
  }, 250)
}

function pause() {
  window.clearInterval(tick)
  running.value = false
}

function timeUp() {
  pause()
  notice.value = 'timeUp' // gentle end: no sound, just a choice
}

function addFive() {
  if (!lengthMin.value) return
  lengthMin.value += 5
  notice.value = null
  if (!running.value) start()
}

function finish() {
  pause()
  const m = Math.max(1, Math.round(elapsed.value / 60)) // stopping early still counts
  activity.logSession(feature.value, m, intent.value || `Focus session in ${FEATURE_LABEL[feature.value]}`)
  savedMinutes.value = m
  elapsed.value = 0
  nudgedAt = 0
  if (!LENGTHS.includes(lengthMin.value as (typeof LENGTHS)[number])) lengthMin.value = 10
  intent.value = ''
  notice.value = 'saved'
}

// the "Start here" card can start a session with its own length and task
watch(() => props.preset?.nonce, () => {
  const p = props.preset
  if (!p || running.value) return
  elapsed.value = 0
  lengthMin.value = p.minutes
  feature.value = p.feature
  intent.value = p.intent
  start()
})

onBeforeUnmount(() => window.clearInterval(tick))
</script>

<template>
  <section class="pd-card pd-timer" aria-labelledby="timer-title">
    <div class="pd-head">
      <h2 id="timer-title">Focus timer</h2>
      <slot name="today" />
    </div>

    <div class="pd-timer-body">
      <svg class="pd-ring" width="132" height="132" viewBox="0 0 132 132" role="img" :aria-label="`Time ${lengthMin ? 'left' : 'so far'}: ${display}`">
        <circle cx="66" cy="66" r="56" fill="none" stroke="var(--pd-empty)" stroke-width="12" />
        <circle cx="66" cy="66" r="56" fill="none" stroke="var(--pd-accent)" stroke-width="12" stroke-linecap="round"
                transform="rotate(-90 66 66)" :stroke-dasharray="CIRC" :stroke-dashoffset="dashOffset" />
        <text v-if="!hideDigits" x="66" y="73" text-anchor="middle" font-size="22">{{ display }}</text>
      </svg>

      <div class="pd-timer-controls">
        <label for="pd-intent" class="pd-muted pd-small">What are you working on?</label>
        <input id="pd-intent" v-model="intent" type="text" maxlength="120" placeholder="e.g. Decode my manager's email" />
        <select v-model="feature" aria-label="Section">
          <option v-for="f in FEATURES" :key="f" :value="f">{{ FEATURE_LABEL[f] }}</option>
        </select>
        <div class="pd-row pd-seg" role="group" aria-label="Session length">
          <button v-for="m in LENGTHS" :key="m" type="button" :aria-pressed="lengthMin === m" @click="setLength(m)">{{ m }}</button>
          <button type="button" :aria-pressed="lengthMin === 0" @click="setLength(0)">Open</button>
        </div>
        <div class="pd-row">
          <button type="button" class="pd-primary" @click="running ? pause() : start()">
            {{ running ? 'Pause' : elapsed ? 'Resume' : 'Start' }}
          </button>
          <button type="button" :disabled="!elapsed" @click="finish">Finish</button>
          <button type="button" class="pd-ghost" :disabled="!elapsed || !lengthMin" @click="addFive">+5 min</button>
        </div>
      </div>
    </div>

    <div v-if="notice" class="pd-notice" role="status">
      <template v-if="notice === 'timeUp'">
        <p>Time's up. Nice work. What would you like to do?</p>
        <div class="pd-row">
          <button type="button" class="pd-primary" @click="finish">Save and take a break</button>
          <button type="button" @click="addFive">5 more minutes</button>
        </div>
      </template>
      <template v-else-if="notice === 'hyperfocus'">
        <p>You've been going for {{ Math.round(elapsed / 60) }} minutes. A good moment to drink some water or stretch?</p>
        <div class="pd-row">
          <button type="button" class="pd-ghost" @click="notice = null">Keep going</button>
          <button type="button" @click="finish">Wrap up</button>
        </div>
      </template>
      <p v-else>Saved {{ savedMinutes }} minute{{ savedMinutes === 1 ? '' : 's' }}. A short break helps it stick.</p>
    </div>

    <label class="pd-toggle pd-small"><input v-model="hideDigits" type="checkbox" /> Hide numbers, just show the ring</label>
  </section>
</template>
