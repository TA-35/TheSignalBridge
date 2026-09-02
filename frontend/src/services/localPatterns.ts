import type { Pattern } from '@/types/pattern'

// Local-only: the phrase this fallback heuristic looks for to notice a
// specific pattern in a message. Not part of the API contract — a real
// classifier only needs to return `category` (see docs/api-contract.md);
// disambiguating between several patterns that share a category is this
// frontend's problem to solve, not the model's.
interface LocalPattern extends Pattern {
  matchHint: RegExp
}

// Seed content used until GET /api/patterns is backed by real RDS rows.
// Category strings here are a subset of the real enum — see
// CATEGORY_TRIGGERS below, which covers all six independently of which
// example patterns happen to exist locally.
export const LOCAL_PATTERNS: LocalPattern[] = [
  {
    id: 'l1',
    name: '"When you get a chance"',
    category: 'Softened request',
    implies:
      'It is a request with a real deadline attached somewhere else in the thread — the softener is politeness, not optionality.',
    why_misread:
      'Read literally, it sounds like "whenever, no rush". The urgency lives in context the sender assumed you shared.',
    matchHint: /when you get a chance/i,
  },
  {
    id: 'l2',
    name: '"Before the sync"',
    category: 'Vague deadline',
    implies: 'A deadline anchored to an event, not a time. The sender assumes you know when that event is.',
    why_misread:
      'Event anchors feel precise to the sender and unknowable to the reader, so the gap goes unnoticed by both.',
    matchHint: /\bbefore\b[^.,!?\n]*/i,
  },
  {
    id: 'l3',
    name: '"Loop in whoever owns it"',
    category: 'Unassigned owner',
    implies: 'Ownership is being handed to you to figure out — the sender does not know either.',
    why_misread:
      'It reads as an instruction you should already be able to follow, when it is actually an open question.',
    matchHint: /\b(loop in|whoever|if that'?s easier)\b/i,
  },
  {
    id: 'l4',
    name: '"Just a few small tweaks"',
    category: 'Feedback framing',
    implies:
      'The scope is unspecified and usually larger than "small" suggests; "just" minimises to keep the tone light.',
    why_misread:
      'Minimisers set an expectation of a 10-minute job, so the real effort feels like your failure rather than a scoping gap.',
    matchHint: /\bjust a few\b|\bsmall tweaks?\b/i,
  },
  {
    id: 'l5',
    name: '"No pressure, but…"',
    category: 'Softened request',
    implies: 'There is pressure. The disclaimer is protecting the relationship, not removing the deadline.',
    why_misread:
      'Explicit denials of urgency are taken at face value, especially when you prefer to read words as written.',
    matchHint: /no pressure/i,
  },
  {
    id: 'l6',
    name: '"EOD" / "sometime this week"',
    category: 'Vague deadline',
    implies: "A specific hour in the sender's timezone and working day, rarely in yours.",
    why_misread: 'Shorthand deadlines look exact, so few people ask which clock they refer to.',
    matchHint: /\beod\b|end of day|\bthis week\b/i,
  },
]

export const PATTERN_CATEGORIES = [...new Set(LOCAL_PATTERNS.map((p) => p.category))]

// Phrase -> category, kept in step with _CATEGORY_RULES in
// backend/app/services/ai_decoder.py so the offline fallback classifies
// identically to the real endpoint. Independent of LOCAL_PATTERNS — a
// category can be detected here even when no local example pattern
// carries it yet (e.g. once the real 25-row library added "Unclear
// priority" and "Undefined scope", these two didn't have local examples).
// Order matters: the first match wins on both sides, so keep them aligned.
const CATEGORY_TRIGGERS: { pattern: RegExp; category: string }[] = [
  { pattern: /when you get a chance/i, category: 'Softened request' },
  { pattern: /\bbefore\b[^.,!?\n]*/i, category: 'Vague deadline' },
  { pattern: /\b(loop in|whoever|if that'?s easier)\b/i, category: 'Unassigned owner' },
  { pattern: /\bjust a few\b|\bsmall tweaks?\b/i, category: 'Feedback framing' },
  { pattern: /no pressure/i, category: 'Softened request' },
  { pattern: /\beod\b|end of day|\bthis week\b/i, category: 'Vague deadline' },
  {
    pattern: /not let it slip|not urgent,? but|prioriti[sz]e|not sure how (?:much|important)/i,
    category: 'Unclear priority',
  },
  { pattern: /\bclean up\b|\btake a pass\b|\btighten up\b|\blook into\b/i, category: 'Undefined scope' },
]

// Category for a message, or null if nothing matches — used for the
// decode contract's `category` field. See CATEGORY_TRIGGERS above.
export function guessCategory(message: string): string | null {
  return CATEGORY_TRIGGERS.find((t) => t.pattern.test(message))?.category ?? null
}

// Finds the specific local pattern a message's wording points to — not
// just its category, so "no pressure" doesn't get silently matched to the
// "when you get a chance" card just because both are Softened requests.
// Only ever returns a pattern from LOCAL_PATTERNS, so it's null for
// categories with no local example yet, even if guessCategory() matched.
export function findLocalPatternMatch(message: string): Pattern | null {
  return LOCAL_PATTERNS.find((p) => p.matchHint.test(message)) ?? null
}
