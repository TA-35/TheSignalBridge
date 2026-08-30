import type { Pattern } from '@/types/pattern'

// Local-only: the phrase this fallback heuristic looks for to notice a
// specific pattern in a message. Not part of the API contract， a real
// classifier only needs to return `category` (see docs/api-contract.md);
// disambiguating between several patterns that share a category is this
// frontend's problem to solve, not the model's.
interface LocalPattern extends Pattern {
  matchHint: RegExp
}

// Seed content used until GET /api/patterns is backed by real RDS rows
// Category strings here are the draft enum
// documented in docs/api-contract.md.
export const LOCAL_PATTERNS: LocalPattern[] = [
  {
    id: 'l1',
    name: '"When you get a chance"',
    category: 'Softened request',
    implies:
      'It is a request with a real deadline attached somewhere else in the thread — the softener is politeness, not optionality.',
    why_misread:
      'Read literally, it sounds like "whenever, no rush". The urgency lives in context the sender assumed you shared.',
    source: 'Brown & Levinson, Politeness: Some Universals in Language Usage (1987) — negative-politeness hedging',
    matchHint: /when you get a chance/i,
  },
  {
    id: 'l2',
    name: '"Before the sync"',
    category: 'Vague deadline',
    implies: 'A deadline anchored to an event, not a time. The sender assumes you know when that event is.',
    why_misread:
      'Event anchors feel precise to the sender and unknowable to the reader, so the gap goes unnoticed by both.',
    source: 'Clark, Using Language (1996) — common-ground assumptions in reference',
    matchHint: /\bbefore\b[^.,!?\n]*/i,
  },
  {
    id: 'l3',
    name: '"Loop in whoever owns it"',
    category: 'Unassigned owner',
    implies: 'Ownership is being handed to you to figure out — the sender does not know either.',
    why_misread:
      'It reads as an instruction you should already be able to follow, when it is actually an open question.',
    source: 'Open corpus: Enron Email Corpus — delegation phrasing patterns',
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
    source: 'Leech, Principles of Pragmatics (1983) — the understatement maxim',
    matchHint: /\bjust a few\b|\bsmall tweaks?\b/i,
  },
  {
    id: 'l5',
    name: '"No pressure, but…"',
    category: 'Softened request',
    implies: 'There is pressure. The disclaimer is protecting the relationship, not removing the deadline.',
    why_misread:
      'Explicit denials of urgency are taken at face value, especially when you prefer to read words as written.',
    source: 'Grice, Logic and Conversation (1975) — implicature over literal content',
    matchHint: /no pressure/i,
  },
  {
    id: 'l6',
    name: '"EOD" / "sometime this week"',
    category: 'Vague deadline',
    implies: "A specific hour in the sender's timezone and working day, rarely in yours.",
    why_misread: 'Shorthand deadlines look exact, so few people ask which clock they refer to.',
    source: 'Open corpus: Avocado Research Email Collection — temporal shorthand',
    matchHint: /\beod\b|end of day|\bthis week\b/i,
  },
]

export const PATTERN_CATEGORIES = [...new Set(LOCAL_PATTERNS.map((p) => p.category))]

// Finds the specific local pattern a message's wording points to
export function findLocalPatternMatch(message: string): Pattern | null {
  return LOCAL_PATTERNS.find((p) => p.matchHint.test(message)) ?? null
}
