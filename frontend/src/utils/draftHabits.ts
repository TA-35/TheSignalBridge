// What a writer's own drafts tend to leave out, so they can see their habits
// and not just fix one message at a time.
//
// Counted in this browser only, and only the kind of gap the what's-missing
// card found (when / who / what / urgency) plus the day - never a word of the
// draft. Nothing is sent or synced. The last 10 drafts are kept, so the picture
// follows how someone writes now, not how they wrote in their first week.
import { dateKey } from './progress'
import type { MissingKey } from './missing'

export interface DraftHabit {
  day: string
  gaps: MissingKey[]
}

const KEY = 'bw-draft-habits'
export const WINDOW = 10
// Fewer drafts than this aren't a pattern yet.
export const MIN_DRAFTS = 3
const KINDS: MissingKey[] = ['when', 'who', 'what', 'urgency']

export function readHabits(): DraftHabit[] {
  try {
    const list: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    if (!Array.isArray(list)) return []
    // Kept to the known shape: an old or hand-edited entry can't put anything else on screen.
    return list
      .filter((d): d is DraftHabit => !!d && typeof d.day === 'string' && Array.isArray(d.gaps))
      .map((d) => ({ day: d.day, gaps: d.gaps.filter((g) => KINDS.includes(g)) }))
      .slice(-WINDOW)
  } catch {
    return []
  }
}

/** One more draft, with the gaps its first rewrite found ([] for a clear one). */
export function recordDraft(gaps: MissingKey[], day = dateKey()): DraftHabit[] {
  const list = [...readHabits(), { day, gaps: [...new Set(gaps.filter((g) => KINDS.includes(g)))] }].slice(-WINDOW)
  try {
    localStorage.setItem(KEY, JSON.stringify(list))
  } catch {
    // Storage blocked: nothing to show, and nothing else breaks.
  }
  return list
}

export function clearHabits(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // nothing stored to remove
  }
}

/** How many of the drafts left each thing out, most often first; none that never happened. */
export function habitSummary(list: DraftHabit[]) {
  const counts = KINDS.map((key) => ({ key, count: list.filter((d) => d.gaps.includes(key)).length }))
    .filter((c) => c.count > 0)
    .sort((a, b) => b.count - a.count || KINDS.indexOf(a.key) - KINDS.indexOf(b.key))
  return { drafts: list.length, counts }
}
