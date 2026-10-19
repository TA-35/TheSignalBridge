// Define response type: Mirrors docs/api-contract.md POST /api/decode.

export type ElementKey = 'time' | 'task' | 'deadline' | 'for_whom'

// The same words the model's rows use (REVIEW_FIELD_LABELS), so the page
// doesn't change vocabulary when the closer reading lands.
export const ELEMENT_LABELS: Record<ElementKey, string> = {
  time: 'When',
  task: 'What needs doing',
  deadline: 'By when',
  for_whom: 'For whom',
}

export const NOT_SPECIFIED = 'Not specified'

export interface MissingElement {
  field: ElementKey
  prompt: string
}

// One ask from the message. A message with three requests returns three,
// each carrying only the fields that sit inside its own clause.
export interface DecodeTask {
  text: string
  span: [number, number]
  time: string
  deadline: string
  for_whom: string
  missing: MissingElement[]
}

export interface DecodeResult {
  elements: Record<ElementKey, string>
  covered: ElementKey[]
  missing: MissingElement[]
  category: string | null
  // Additive to the v1 contract; absent when the offline decoder answered.
  tasks?: DecodeTask[]
  spans?: Partial<Record<ElementKey, [number, number] | null>>
}

// A decode the user actually ran, kept so the work survives the session and
// a flashcard can point back at the message that produced it.
//
// Local only. This is the one place message text is written to disk - see
// the data-retention note in docs/api-contract.md.
export interface DecodeRecord {
  id: string
  createdAt: string
  message: string
  tasks: DecodeTask[]
  elements: Record<ElementKey, string>
  missing: MissingElement[]
  // Gaps the user ticked - the questions they decided were worth asking.
  /** Field names the user ticked. Widened from ElementKey because the
   *  gap list is model-keyed once the review lands, and the two sources
   *  name the same field differently ("task" / "required_action"). */
  asked: string[]
  category: string | null
  patternId: string | null
}
