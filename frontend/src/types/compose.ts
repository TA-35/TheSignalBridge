// Mirrors POST /api/compose and /api/compose/quick - see docs/api-contract.md.
//
// Compose is the other direction from Decode. The reader pastes a message
// they have already written, and gets it back saying the same thing more
// explicitly, plus a short account of what changed.
//
// The shape comes from the training record in the data team's build guide:
// the model is trained to emit exactly `meaning`, `rewrite` and `notes`, so
// these names are not ours to rename.

/** What the three classifiers made of the draft. Advisory - the prompt tells
 *  the model they may be wrong. */
export interface ComposeSignal {
  model: 'tone' | 'politeness' | 'circa' | string
  label: string
  confidence: number
}

/** The model's read of the draft, as five fixed fields. `tone` is an
 *  observation about the message, never an instruction: the rewrite keeps
 *  the sender's register and only makes the content explicit. */
export interface ComposeMeaning {
  ask: string
  deadline: string
  urgency: 'low' | 'medium' | 'high' | ''
  tone: string
  implied: string
}

/** Stage one: classifier signals only, no model call. Milliseconds. */
export interface ComposeQuick {
  stage: 'analyse'
  signals: ComposeSignal[]
}

/** Stage two: the rewrite.
 *
 *  `rewrite` is null when there is nothing safe to show - the grounding
 *  check found a dropped or invented fact, or the service was unreachable.
 *  A rewrite that failed verification must never be rendered: it reads as
 *  finished text and would be copied straight into an email. */
export interface ComposeResult {
  stage: 'compose'
  degraded: boolean
  degraded_reason?: string[]
  rewrite: string | null
  notes: string[]
  meaning: ComposeMeaning
  signals?: ComposeSignal[]
  /** What the grounding check verified. Present on an undegraded answer. */
  checks?: {
    entities_kept: boolean
    nothing_added: boolean
  }
  model?: string
}

/** The exact note the model returns when the draft needed no changes. Set in
 *  the shared generation prompt, so it is a value to compare against rather
 *  than prose to render as a change. */
export const ALREADY_CLEAR = 'Already clear, kept as written.'

export function isAlreadyClear(result: ComposeResult): boolean {
  return result.notes.length === 1 && result.notes[0] === ALREADY_CLEAR
}
