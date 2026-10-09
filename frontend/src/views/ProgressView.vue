<script setup lang="ts">
// Progress dashboard. Calm by design: one next step, gentle reminders,
// badges for total days used (never streaks), and no missed days anywhere.
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import FocusTimer from '@/components/progress/FocusTimer.vue'
import { useProgressSources } from '@/composables/useProgressSources'
import {
  BADGES, FEATURES, badgeStatus, dateKey, dueForReview, libraryProgress, nextStep,
  progressByCategory, reviewReminder, usageByDay, type Energy, type Feature,
} from '@/utils/progress'

// TODO(wire-up): replace these two with the real cards store once connected
const { cards, activity } = useProgressSources(() => [], () => [])

const router = useRouter()
const today = ref(dateKey())

const FEATURE_LABEL: Record<Feature, string> = { decoder: 'Decoder', compose: 'Compose', study: 'Study', library: 'Library' }

// ---------------------------------------------------------------- display settings (this browser only)
function readFlag(k: string) { try { return localStorage.getItem(k) === '1' } catch { return false } }
function saveFlag(k: string, v: boolean) { try { localStorage.setItem(k, v ? '1' : '0') } catch { /* ignore */ } }
const largeText = ref(readFlag('bw-progress-large'))
const hideBadges = ref(readFlag('bw-progress-nobadges'))
watch(largeText, (v) => saveFlag('bw-progress-large', v))
watch(hideBadges, (v) => saveFlag('bw-progress-nobadges', v))

// ---------------------------------------------------------------- start here
const energy = ref<Energy>('okay')
const due = computed(() => dueForReview(cards.value, today.value))
const step = computed(() => nextStep(energy.value, due.value, cards.value, activity.events))
const timerPreset = ref<{ minutes: number; feature: Feature; intent: string; nonce: number }>()
function startStep() {
  timerPreset.value = { ...step.value, nonce: Date.now() }
  document.getElementById('timer-title')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
const lastSession = computed(() => activity.events.at(-1))

// ---------------------------------------------------------------- refresher, as points
const reminder = computed(() => reviewReminder(due.value))
const snoozedToday = ref(sessionStorageGet('bw-refresher-later') === today.value)
function sessionStorageGet(k: string) { try { return sessionStorage.getItem(k) } catch { return null } }
function later() {
  snoozedToday.value = true
  try { sessionStorage.setItem('bw-refresher-later', today.value) } catch { /* ignore */ }
}
function reviewNow() {
  // TODO(wire-up): use the Study route name from the router
  router.push({ path: '/study', query: { review: reminder.value?.cards.map((c) => c.id).join(',') } })
}
const ago = (d: number) => (d === 1 ? '1 day ago' : `${d} days ago`)

// ---------------------------------------------------------------- days shown up + badges
const badges = computed(() => badgeStatus(activity.openDays))
const dots = computed(() => {
  const b = badges.value
  const target = b.next ? b.next.days : b.prevDays
  return Array.from({ length: target - b.prevDays }, (_, i) => b.prevDays + i + 1 <= b.total)
})

// ---------------------------------------------------------------- things you've done
const recent = computed(() => [...activity.events].filter((e) => e.intent).reverse().slice(0, 5))
const shortDate = (k: string) =>
  k === today.value ? 'Today' : new Date(`${k}T00:00`).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
const todayMinutes = computed(() => activity.events.filter((e) => e.date === today.value).reduce((a, e) => a + e.minutes, 0))

// ---------------------------------------------------------------- pattern library
const lib = computed(() => libraryProgress(cards.value))
const byCat = computed(() => progressByCategory(cards.value))
const CAT_COLOURS = ['--pd-c1', '--pd-c2', '--pd-c3', '--pd-c4', '--pd-c5', '--pd-c6']
const DONUT_C = 2 * Math.PI * 58
const donut = computed(() => {
  const l = lib.value
  if (!l.total) return []
  let off = 0
  return ([['mastered', '--pd-learned'], ['saved', '--pd-saved'], ['explored', '--pd-opened']] as const).map(([k, colour]) => {
    const len = (l[k] / l.total) * DONUT_C
    const seg = { len, off, colour }
    off += len
    return seg
  })
})
const pct = (n: number, total: number) => (total ? `${(n / total) * 100}%` : '0%')

// ---------------------------------------------------------------- time by feature chart
const usage = computed(() => usageByDay(activity.events, today.value, 14))
const chartTop = computed(() => Math.ceil(Math.max(30, ...usage.value.map((r) => r.total)) / 15) * 15)
const CH = { w: 640, h: 220, l: 34, b: 28, t: 10 }
const plotH = CH.h - CH.b - CH.t
const barW = (CH.w - CH.l - 8) / 14
const gridLines = computed(() => [0, 1, 2, 3].map((i) => (chartTop.value / 3) * i))
const yOf = (v: number) => CH.t + plotH - (v / chartTop.value) * plotH
function stack(row: (typeof usage.value)[number]) {
  let y = CH.t + plotH
  return FEATURES.filter((f) => row[f] > 0).map((f) => {
    const h = (row[f] / chartTop.value) * plotH
    y -= h
    return { f, y, h, minutes: row[f] }
  })
}
const dayLabel = (k: string) =>
  k === today.value ? 'Today' : `${new Date(`${k}T00:00`).toLocaleDateString('en-AU', { weekday: 'short' }).slice(0, 2)} ${Number(k.slice(8))}`

onMounted(() => {
  activity.markOpenedToday()
  today.value = dateKey()
})
</script>

<template>
  <div class="pd-page" :class="{ 'pd-large': largeText }">
    <header class="pd-header">
      <h1>Your progress</h1>
      <div class="pd-settings">
        <label class="pd-toggle"><input v-model="largeText" type="checkbox" /> Larger text</label>
        <label class="pd-toggle"><input v-model="hideBadges" type="checkbox" /> Hide badges</label>
      </div>
    </header>

    <!-- one next step -->
    <section class="pd-card pd-start" aria-labelledby="start-title">
      <div class="pd-head">
        <h2 id="start-title">Start here</h2>
        <span v-if="lastSession" class="pd-muted pd-small">Last session: {{ FEATURE_LABEL[lastSession.feature] }}</span>
      </div>
      <p class="pd-muted pd-small">How much energy do you have right now?</p>
      <div class="pd-row pd-seg" role="group" aria-label="Energy level">
        <button v-for="e in (['low', 'okay', 'good'] as const)" :key="e" type="button" :aria-pressed="energy === e" @click="energy = e">
          {{ e[0].toUpperCase() + e.slice(1) }}
        </button>
      </div>
      <div class="pd-step">
        <p>{{ step.text }}</p>
        <button type="button" class="pd-primary" @click="startStep">Start</button>
      </div>
    </section>

    <!-- refresher, as points -->
    <section v-if="reminder && !snoozedToday" class="pd-card pd-refresh" aria-labelledby="refresh-title" aria-live="polite">
      <div>
        <div class="pd-eyebrow">Time for a refresher</div>
        <h2 id="refresh-title" class="pd-refresh-head">{{ reminder.heading }}</h2>
        <ul class="pd-review-list">
          <li v-for="g in reminder.groups" :key="g.category">
            <div class="pd-review-cat">
              <strong>{{ g.category }}</strong>
              <span class="pd-muted pd-small">{{ g.cards.length }} card{{ g.cards.length === 1 ? '' : 's' }} · last looked {{ ago(g.daysSince) }}</span>
            </div>
            <ul>
              <li v-for="c in g.cards" :key="c.id">“{{ c.text }}”</li>
            </ul>
          </li>
        </ul>
        <p v-if="reminder.moreCount" class="pd-muted pd-small">and {{ reminder.moreCount }} more after these</p>
      </div>
      <div class="pd-row">
        <button type="button" class="pd-primary" @click="reviewNow">Review ({{ reminder.minutes }} min)</button>
        <button type="button" class="pd-ghost" @click="later">Later</button>
      </div>
    </section>

    <div class="pd-grid2">
      <FocusTimer :preset="timerPreset">
        <template #today><span class="pd-muted pd-small">{{ todayMinutes }} min today</span></template>
      </FocusTimer>

      <section v-if="!hideBadges" class="pd-card pd-days" aria-labelledby="days-title">
        <div class="pd-head">
          <h2 id="days-title">Days you've shown up</h2>
          <span class="pd-muted pd-small">Any day counts</span>
        </div>
        <div><span class="pd-big">{{ badges.total }}</span> <span class="pd-muted">day{{ badges.total === 1 ? '' : 's' }} so far</span></div>
        <div class="pd-dots" aria-hidden="true"><i v-for="(on, i) in dots" :key="i" :class="{ on }" /></div>
        <p class="pd-small">
          <template v-if="badges.next">{{ badges.daysToNext }} more day{{ badges.daysToNext === 1 ? '' : 's' }} until your {{ badges.next.name }} badge.</template>
          <template v-else>You've earned every badge.</template>
        </p>
        <p class="pd-muted pd-small">Days don't need to be in a row. Come back whenever suits you and it still counts.</p>
      </section>
    </div>

    <section class="pd-card" aria-labelledby="done-title">
      <div class="pd-head"><h2 id="done-title">Things you've done</h2><span class="pd-muted pd-small">Your last few sessions</span></div>
      <ul v-if="recent.length" class="pd-wins">
        <li v-for="(e, i) in recent" :key="i">
          <span><i class="pd-dot" :style="{ background: `var(--pd-f-${e.feature})` }" />{{ e.intent }}</span>
          <span class="pd-muted pd-small pd-num">{{ e.minutes }} min · {{ shortDate(e.date) }}</span>
        </li>
      </ul>
      <p v-else class="pd-muted">Your finished focus sessions will show up here. Try a 5 minute one to start.</p>
    </section>

    <section class="pd-card" aria-labelledby="lib-title">
      <div class="pd-head">
        <h2 id="lib-title">Pattern library</h2>
        <span class="pd-muted pd-small">{{ lib.saved + lib.mastered }} in my cards · {{ lib.opened }} of {{ lib.total }} opened</span>
      </div>
      <div v-if="lib.total" class="pd-lib">
        <svg width="150" height="150" viewBox="0 0 150 150" role="img" :aria-label="`${lib.percentExplored}% of the library explored`">
          <circle cx="75" cy="75" r="58" fill="none" stroke="var(--pd-empty)" stroke-width="16" />
          <circle v-for="s in donut" :key="s.colour" cx="75" cy="75" r="58" fill="none" :stroke="`var(${s.colour})`" stroke-width="16"
                  :stroke-dasharray="`${s.len} ${DONUT_C - s.len}`" :stroke-dashoffset="-s.off" transform="rotate(-90 75 75)" />
          <text x="75" y="80" text-anchor="middle" class="pd-donut-num">{{ lib.percentExplored }}%</text>
          <text x="75" y="100" text-anchor="middle" class="pd-svg-muted">explored</text>
        </svg>
        <div class="pd-cats">
          <div v-for="(c, i) in byCat" :key="c.category" class="pd-cat">
            <div class="pd-head pd-small">
              <span class="pd-mono"><i class="pd-dot" :style="{ background: `var(${CAT_COLOURS[i % 6]})` }" />{{ c.category }}</span>
              <span class="pd-muted pd-num">{{ c.opened }}/{{ c.total }} opened</span>
            </div>
            <div class="pd-stack">
              <span :style="{ width: pct(c.mastered, c.total), background: 'var(--pd-learned)' }" />
              <span :style="{ width: pct(c.saved, c.total), background: 'var(--pd-saved)' }" />
              <span :style="{ width: pct(c.explored, c.total), background: 'var(--pd-opened)' }" />
            </div>
          </div>
        </div>
      </div>
      <p v-else class="pd-muted">Open a few phrases in the Library to see your progress here.</p>
      <div class="pd-legend">
        <span><b style="background: var(--pd-learned)" />Learned (saved, reviewed 3+ times)</span>
        <span><b style="background: var(--pd-saved)" />In my cards</span>
        <span><b style="background: var(--pd-opened)" />Opened</span>
        <span><b style="background: var(--pd-empty)" />Not opened yet</span>
      </div>
    </section>

    <section class="pd-card" aria-labelledby="usage-title">
      <div class="pd-head"><h2 id="usage-title">Time by feature</h2><span class="pd-muted pd-small">Last 14 days, minutes</span></div>
      <div class="pd-scroll">
        <svg :viewBox="`0 0 ${CH.w} ${CH.h}`" class="pd-chart" role="img" aria-label="Minutes per day by feature, last 14 days">
          <g v-for="v in gridLines" :key="v">
            <line :x1="CH.l" :x2="CH.w" :y1="yOf(v)" :y2="yOf(v)" stroke="var(--pd-line)" />
            <text :x="CH.l - 6" :y="yOf(v) + 4" text-anchor="end" class="pd-svg-muted">{{ Math.round(v) }}</text>
          </g>
          <g v-for="(row, i) in usage" :key="row.date">
            <rect v-for="s in stack(row)" :key="s.f" :x="CH.l + 4 + i * barW" :y="s.y" :width="barW - 8" :height="s.h" :fill="`var(--pd-f-${s.f})`">
              <title>{{ row.date }} {{ FEATURE_LABEL[s.f] }}: {{ s.minutes }} min</title>
            </rect>
            <text :x="CH.l + 4 + i * barW + (barW - 8) / 2" :y="CH.h - 8" text-anchor="middle" class="pd-svg-muted">{{ dayLabel(row.date) }}</text>
          </g>
        </svg>
      </div>
      <div class="pd-legend">
        <span v-for="f in FEATURES" :key="f"><b :style="{ background: `var(--pd-f-${f})` }" />{{ FEATURE_LABEL[f] }}</span>
      </div>
    </section>

    <section v-if="!hideBadges" class="pd-card" aria-labelledby="badges-title">
      <div class="pd-head"><h2 id="badges-title">Badges</h2><span class="pd-muted pd-small">Earned by total days, never taken away</span></div>
      <div class="pd-badges">
        <div v-for="b in BADGES" :key="b.id" class="pd-badge" :class="{ locked: badges.total < b.days }">
          <svg viewBox="0 0 44 44" aria-hidden="true">
            <path d="M22 3 L38 12 V30 L22 41 L6 30 V12 Z" :fill="`var(--pd-${b.id})`" />
            <path d="M22 12 l3 6.5 7 .8-5.2 4.8 1.4 7-6.2-3.6-6.2 3.6 1.4-7L12 19.3l7-.8z" fill="var(--pd-surface)" opacity=".85" />
          </svg>
          <strong>{{ b.name }}</strong>
          <small>{{ b.days }} days</small>
          <small>{{ badges.total >= b.days ? 'Earned' : `${b.days - badges.total} to go` }}</small>
        </div>
      </div>
    </section>
  </div>
</template>

<style>
/* Tokens for the progress page. Calm palette: no red, each section its own soft colour.
   Not scoped, so FocusTimer (a child component) shares them. All prefixed pd- to avoid clashes. */
.pd-page {
  --pd-bg: #ece9e3; --pd-surface: #fbfaf7; --pd-ink: #23302b; --pd-muted-c: #5e6863; --pd-line: #ddd8cf;
  --pd-empty: #e4e0d8;
  --pd-teal: #3d8790; --pd-teal-soft: #ddeef0;
  --pd-lavender: #7466a8; --pd-lavender-soft: #ece9f6;
  --pd-honey: #a88442; --pd-honey-soft: #f4ecdc;
  --pd-heather: #86698b; --pd-heather-soft: #f0e8f0;
  --pd-learned: #5e8a70; --pd-saved: #6f92c8; --pd-opened: #e9cf98;
  --pd-f-decoder: #3d8790; --pd-f-compose: #a88442; --pd-f-study: #6c8ebf; --pd-f-library: #9b7bb4;
  --pd-c1: #3d8790; --pd-c2: #a88442; --pd-c3: #5e8a70; --pd-c4: #4a6fa5; --pd-c5: #7466a8; --pd-c6: #93708f;
  --pd-iron: #7a8288; --pd-bronze: #a8693a; --pd-silver: #9aa5ae; --pd-gold: #c9a227; --pd-diamond: #4fa3c7;
  --pd-accent: var(--pd-teal); --pd-accent-soft: var(--pd-teal-soft);
  --pd-base: 16px;
  font-size: var(--pd-base);
  color: var(--pd-ink);
  max-width: 980px; margin: 0 auto; padding-block: 24px 48px; display: grid; gap: 18px;
}
@media (prefers-color-scheme: dark) {
  .pd-page {
    --pd-bg: #161a18; --pd-surface: #1e2421; --pd-ink: #e8e6e1; --pd-muted-c: #a2a9a4; --pd-line: #2f3632; --pd-empty: #2a312d;
    --pd-teal: #7cc3cc; --pd-teal-soft: #1c3033; --pd-lavender: #ada2de; --pd-lavender-soft: #26233a;
    --pd-honey: #d9b577; --pd-honey-soft: #33291a; --pd-heather: #c7a9cb; --pd-heather-soft: #2c2330;
    --pd-learned: #9cc2ab; --pd-saved: #8fb0e0; --pd-opened: #6b5a33;
    --pd-f-decoder: #7cc3cc; --pd-f-compose: #d9b577; --pd-f-study: #8fb0e0; --pd-f-library: #c3a3dc;
  }
}
.pd-page.pd-large { --pd-base: 19px; }
.pd-page h1 { font-size: 2.2em; margin: 0; }
.pd-page h2 { font-size: 1.1em; margin: 0; font-weight: 600; }
.pd-header { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; justify-content: space-between; }
.pd-settings { display: flex; gap: 16px; flex-wrap: wrap; }
.pd-toggle { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.pd-toggle input { width: 18px; height: 18px; accent-color: var(--pd-accent); }
.pd-card { background: var(--pd-surface); border: 1px solid var(--pd-line); border-radius: 14px; padding: 20px; display: grid; gap: 14px; min-width: 0; }
.pd-grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }
.pd-head { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.pd-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.pd-muted { color: var(--pd-muted-c); }
.pd-small { font-size: .88em; }
.pd-num { font-variant-numeric: tabular-nums; }
.pd-mono { font-family: ui-monospace, 'IBM Plex Mono', monospace; font-size: .9em; }
.pd-eyebrow { font-family: ui-monospace, 'IBM Plex Mono', monospace; font-size: .8em; color: var(--pd-muted-c); }
.pd-page p { margin: 0; }
.pd-page button { font: inherit; font-size: .92em; font-weight: 600; border-radius: 10px; padding: 9px 16px; cursor: pointer;
  border: 1px solid var(--pd-line); background: var(--pd-surface); color: var(--pd-ink); }
.pd-page button.pd-primary { background: var(--pd-accent); border-color: var(--pd-accent); color: var(--pd-surface); }
.pd-page button.pd-ghost { border-color: transparent; color: var(--pd-accent); padding-inline: 8px; }
.pd-page button:disabled { opacity: .5; cursor: default; }
.pd-page button:focus-visible, .pd-page input:focus-visible, .pd-page select:focus-visible { outline: 3px solid var(--pd-accent); outline-offset: 2px; }
.pd-seg button[aria-pressed='true'] { background: var(--pd-accent-soft); border-color: var(--pd-accent); color: var(--pd-accent); }
.pd-page input[type='text'], .pd-page select { font: inherit; font-size: .95em; padding: 9px 12px; border-radius: 10px; border: 1px solid var(--pd-line);
  background: var(--pd-surface); color: var(--pd-ink); width: 100%; }

.pd-start { --pd-accent: var(--pd-teal); --pd-accent-soft: var(--pd-teal-soft); border-left: 5px solid var(--pd-accent); }
.pd-step { display: grid; grid-template-columns: 1fr auto; gap: 14px; align-items: center; padding: 14px; border-radius: 12px; background: var(--pd-accent-soft); }
.pd-step p { font-size: 1.05em; max-width: 60ch; }

.pd-refresh { --pd-accent: var(--pd-lavender); --pd-accent-soft: var(--pd-lavender-soft); border-left: 5px solid var(--pd-accent);
  grid-template-columns: 1fr auto; align-items: start; }
.pd-refresh-head { font-size: 1.25em !important; margin-top: 4px !important; }
.pd-review-list { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 12px; }
.pd-review-list > li { padding-left: 14px; border-left: 3px solid var(--pd-accent-soft); }
.pd-review-cat { display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; }
.pd-review-list ul { margin: 4px 0 0; padding-left: 18px; }
.pd-review-list ul li { margin: 2px 0; }

.pd-timer { --pd-accent: var(--pd-heather); --pd-accent-soft: var(--pd-heather-soft); }
.pd-timer-body { display: grid; grid-template-columns: auto 1fr; gap: 20px; align-items: center; }
.pd-timer-controls { display: grid; gap: 10px; min-width: 0; }
.pd-ring text { fill: var(--pd-ink); }
.pd-notice { padding: 12px 14px; border-radius: 10px; background: var(--pd-accent-soft); display: grid; gap: 10px; }

.pd-days { --pd-accent: var(--pd-honey); --pd-accent-soft: var(--pd-honey-soft); }
.pd-big { font-size: 3em; line-height: 1; font-weight: 600; color: var(--pd-honey); font-variant-numeric: tabular-nums; }
.pd-dots { display: flex; flex-wrap: wrap; gap: 6px; }
.pd-dots i { width: 14px; height: 14px; border-radius: 50%; background: var(--pd-empty); }
.pd-dots i.on { background: var(--pd-accent); }

.pd-wins { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }
.pd-wins li { display: flex; justify-content: space-between; gap: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--pd-line); }
.pd-wins li:last-child { border-bottom: 0; padding-bottom: 0; }
.pd-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; vertical-align: 1px; }

.pd-lib { display: grid; grid-template-columns: auto 1fr; gap: 20px; align-items: center; }
.pd-cats { display: grid; gap: 12px; min-width: 0; }
.pd-cat { display: grid; gap: 4px; }
.pd-stack { display: flex; height: 10px; border-radius: 999px; overflow: hidden; background: var(--pd-empty); }
.pd-donut-num { font-size: 26px; font-weight: 600; fill: var(--pd-ink); }
.pd-svg-muted { fill: var(--pd-muted-c); font-size: 11px; }
.pd-legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: .82em; color: var(--pd-muted-c); align-items: center; }
.pd-legend b { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }

.pd-scroll { overflow-x: auto; }
.pd-chart { width: 100%; min-width: 520px; height: auto; }

.pd-badges { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; }
.pd-badge { border: 1px solid var(--pd-line); border-radius: 12px; padding: 14px; display: grid; gap: 4px; justify-items: center; text-align: center; }
.pd-badge.locked { opacity: .45; }
.pd-badge svg { width: 44px; height: 44px; }
.pd-badge small { color: var(--pd-muted-c); }

@media (max-width: 560px) {
  .pd-step, .pd-refresh { grid-template-columns: 1fr; }
  .pd-lib, .pd-timer-body { grid-template-columns: 1fr; justify-items: center; }
  .pd-cats, .pd-timer-controls { width: 100%; }
}
@media (prefers-reduced-motion: reduce) { .pd-page * { transition: none !important; scroll-behavior: auto !important; } }
</style>
