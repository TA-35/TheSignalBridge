// Progress dashboard maths. Kept separate from the Vue page so it's easy to test.
// Everything works off two things we already have on the device:
//   - activity events (which day someone used which feature, and for how long)
//   - saved study cards (which category, and the days they were reviewed)
// Nothing here needs an account or sends anything to the server.

export type Feature = 'decoder' | 'compose' | 'study' | 'library'
export const FEATURES: Feature[] = ['decoder', 'compose', 'study', 'library']

export interface ActivityEvent {
  date: string // YYYY-MM-DD in the user's local time
  feature: Feature
  minutes: number
  intent?: string // what they said they were working on (timer only)
}

export interface CardProgress {
  id: string
  text: string
  category: string
  saved: boolean // in "my cards"
  viewed: boolean // opened "See what this means"
  reviews: string[] // dates it was reviewed in Study
}

// ---------------------------------------------------------------- dates
export function dateKey(d: Date = new Date()): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function parseKey(k: string): Date {
  const [y, m, d] = k.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function addDays(k: string, n: number): string {
  const d = parseKey(k)
  d.setDate(d.getDate() + n)
  return dateKey(d)
}

export function daysBetween(a: string, b: string): number {
  return Math.round((parseKey(b).getTime() - parseKey(a).getTime()) / 86400000)
}

// ---------------------------------------------------------------- badges
// Badges count total days the user opened Between Words. Days don't need to be
// in a row and we never show missed days, so there's nothing to "lose".
export const BADGES = [
  { id: 'iron', name: 'Iron', days: 7 },
  { id: 'bronze', name: 'Bronze', days: 15 },
  { id: 'silver', name: 'Silver', days: 45 },
  { id: 'gold', name: 'Gold', days: 100 },
  { id: 'diamond', name: 'Diamond', days: 180 },
] as const
export type Badge = (typeof BADGES)[number]

// openDays = every date the app was opened (recorded once per day on load)
export function badgeStatus(openDays: string[]) {
  const total = new Set(openDays).size
  const earned = BADGES.filter((b) => total >= b.days)
  const next = BADGES.find((b) => total < b.days) ?? null
  const prevDays = earned.length ? earned[earned.length - 1].days : 0
  return {
    total,
    earned,
    next,
    prevDays,
    daysToNext: next ? next.days - total : 0,
    // progress inside the current band, e.g. 12 days = 5 of the 8 between Iron and Bronze
    progress: next ? (total - prevDays) / (next.days - prevDays) : 1,
  }
}

// ---------------------------------------------------------------- pattern library
export type CardState = 'mastered' | 'saved' | 'explored' | 'notOpened'
export const MASTERED_AT = 3 // reviews in Study before a card counts as learned

export function cardState(c: CardProgress): CardState {
  if (c.saved && c.reviews.length >= MASTERED_AT) return 'mastered'
  if (c.saved) return 'saved'
  if (c.viewed) return 'explored'
  return 'notOpened'
}

export function libraryProgress(cards: CardProgress[]) {
  const out = { mastered: 0, saved: 0, explored: 0, notOpened: 0, total: cards.length }
  for (const c of cards) out[cardState(c)]++
  const opened = out.total - out.notOpened
  return { ...out, opened, percentExplored: out.total ? Math.round((opened / out.total) * 100) : 0 }
}

export function progressByCategory(cards: CardProgress[]) {
  const groups = new Map<string, CardProgress[]>()
  for (const c of cards) groups.set(c.category, [...(groups.get(c.category) ?? []), c])
  return [...groups.entries()].map(([category, list]) => ({ category, ...libraryProgress(list) }))
}

// ---------------------------------------------------------------- forgetting curve
// Ebbinghaus style: retention = e^(-t/S). Stability S starts at 1.5 days and
// doubles with every review, so gaps grow roughly 1, 2, 5, 10, 20 days.
// A saved card is due once its estimated retention drops under 70%.
export interface DueCard extends CardProgress {
  retention: number
  daysSince: number
}

export function retention(c: CardProgress, today: string, base = 1.5) {
  if (!c.reviews.length) return null
  const last = [...c.reviews].sort().at(-1) as string
  const daysSince = daysBetween(last, today)
  const stability = base * 2 ** (c.reviews.length - 1)
  return { retention: Math.exp(-daysSince / stability), daysSince }
}

export function dueForReview(cards: CardProgress[], today: string, threshold = 0.7): DueCard[] {
  const due: DueCard[] = []
  for (const c of cards) {
    if (!c.saved) continue
    const r = retention(c, today)
    if (r && r.retention < threshold) due.push({ ...c, ...r })
  }
  return due.sort((a, b) => a.retention - b.retention)
}

// The refresher card, shown as points grouped by category rather than one long sentence
export function reviewReminder(due: DueCard[], maxCards = 5) {
  if (!due.length) return null
  const cards = due.slice(0, maxCards)
  const order: string[] = []
  for (const c of cards) if (!order.includes(c.category)) order.push(c.category)
  const groups = order.map((category) => {
    const inCat = cards.filter((c) => c.category === category)
    return { category, cards: inCat, daysSince: Math.max(...inCat.map((c) => c.daysSince)) }
  })
  return {
    heading: `${cards.length} saved card${cards.length === 1 ? '' : 's'} to refresh`,
    groups,
    cards,
    moreCount: due.length - cards.length,
    minutes: Math.max(2, Math.ceil(cards.length * 1.5)),
  }
}

// ---------------------------------------------------------------- usage over time
export type DayUsage = { date: string; total: number } & Record<Feature, number>

export function usageByDay(events: ActivityEvent[], today: string, days = 14): DayUsage[] {
  const rows: DayUsage[] = []
  for (let i = days - 1; i >= 0; i--) {
    rows.push({ date: addDays(today, -i), total: 0, decoder: 0, compose: 0, study: 0, library: 0 })
  }
  const byDate = new Map(rows.map((r) => [r.date, r]))
  for (const e of events) {
    const row = byDate.get(e.date)
    if (!row) continue
    row[e.feature] += e.minutes
    row.total += e.minutes
  }
  return rows
}

// ---------------------------------------------------------------- one next step
export type Energy = 'low' | 'okay' | 'good'
export interface NextStep {
  text: string
  minutes: number
  feature: Feature
  intent: string
}

export function nextStep(energy: Energy, due: DueCard[], cards: CardProgress[], events: ActivityEvent[]): NextStep {
  const last = [...events].filter((e) => e.intent).sort((a, b) => (a.date < b.date ? -1 : 1)).at(-1)
  if (energy === 'low') {
    return due.length
      ? { text: `Just one thing: look over ${due.length === 1 ? 'one saved card' : 'two of your saved cards'} in Study. Five minutes is plenty.`,
          minutes: 5, feature: 'study', intent: 'Reviewed a couple of saved cards' }
      : { text: 'Just one thing: decode one message you got today. Five minutes is plenty.',
          minutes: 5, feature: 'decoder', intent: 'Decoded one message' }
  }
  if (energy === 'good') {
    const cats = progressByCategory(cards).sort((a, b) => b.notOpened - a.notOpened)
    const fresh = cats[0]
    if (fresh && fresh.notOpened > 0) {
      return { text: `You've got some energy, so try a category you haven't explored much: ${fresh.category} (${fresh.opened} of ${fresh.total} opened). Save any phrases you want to come back to.`,
               minutes: 15, feature: 'library', intent: `Explored ${fresh.category}` }
    }
    return { text: 'Try rewriting a message you need to send this week in Compose. 15 minutes.',
             minutes: 15, feature: 'compose', intent: 'Rewrote a message in Compose' }
  }
  if (last?.intent) {
    return { text: `Pick up where you left off: "${last.intent}". 10 minutes.`,
             minutes: 10, feature: last.feature, intent: last.intent }
  }
  return { text: 'Try decoding one message. 10 minutes.', minutes: 10, feature: 'decoder', intent: 'Decoded a message' }
}
