// Mirrors GET /api/patterns
// the curated pattern-library row.
// Read-only content; never carries user data.

export interface Pattern {
  id: string
  name: string
  category: string
  implies: string
  why_misread: string
}

// A card the user has explicitly chosen to keep. Lives only in localStorage.
//
// A card is a record of an encounter, not a library row: it points back at the
// decode that produced it and carries the message excerpt and the gaps the
// user flagged. The pattern fields are null when the wording matched nothing
// in the library - that card is still worth keeping, because what the message
// left unsaid is the lesson.
export interface SavedCard {
  id: string
  decodeId: string | null

  patternId: string | null
  name: string
  category: string | null
  implies: string | null
  why_misread: string | null

  excerpt: string
  unsaid: { field: string; prompt: string }[]
  // The model's reading of the message, when it had answered by the time the
  // card was made (or arrived while the page was still open). Local only, like
  // the excerpt: a card from a decode never syncs.
  meaning?: string | null
  readings?: CardReading[]

  savedAt: string
  lastOpened: string | null
}

/** One claim as the card keeps it: "By when: “Friday” - stated, but not a time…" */
export interface CardReading {
  label: string
  text: string
  reading: string
}
