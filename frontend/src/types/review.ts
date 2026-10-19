// Mirrors POST /api/review and /api/review/quick - see docs/api-contract.md.
//
// Additive to decode.ts. The DecodeResult contract that /api/decode returns
// is unchanged and still used; this is a second, richer reading that arrives
// later and replaces the first stage in place.

/** The six fields the pipeline looks for. Kept in step with FIELDS in
 *  Src/source/pipeline/analysis.py - the response schema constrains the
 *  model to exactly these. */
export type ReviewField =
  | 'purpose'
  | 'required_action'
  | 'responsible_person'
  | 'deadline'
  | 'priority'
  | 'context'

export const REVIEW_FIELD_LABELS: Record<ReviewField, string> = {
  purpose: 'Purpose',
  required_action: 'What needs doing',
  responsible_person: 'Who',
  deadline: 'By when',
  priority: 'Priority',
  context: 'Background',
}

export type MessageType = 'request' | 'update' | 'commitment' | 'social'

/** One thing found in the message. `span` indexes the ORIGINAL message and is
 *  verified server-side: message.slice(span[0], span[1]) === text. Anything
 *  that could not be verified was dropped before it reached here. */
export interface ReviewClaim {
  field: ReviewField
  text: string
  span: [number, number]
  reading?: string
}

/** A field the message leaves unsettled, and the question that would settle
 *  it. Decided by the model, not by the extractor's keyword rules.
 *
 *  There is no span here and there cannot be: a gap is the absence of text,
 *  so there is nothing to quote. `question` is verified for invented names
 *  but is deliberately free to reason about what the message left vague -
 *  a question about a missing deadline has to be able to mention times the
 *  message never stated. */
export interface ReviewGap {
  field: ReviewField
  question: string
}

/** Stage one. Extractor only, no model call - arrives in milliseconds. */
export interface QuickReview {
  stage: 'analyse'
  message_type: MessageType
  extraction: {
    found: Record<string, { field: string; value: string; span: [number, number] }>
    missing: string[]
    actions: { field: string; value: string; span: [number, number] }[]
  }
  comments: { model: string; label: string; confidence: number; note: string }[]
}

/** Stage two. The full reading, including the model. Seconds.
 *
 *  `degraded` is the field that matters: true means the model's answer failed
 *  verification (or never arrived) and what is shown came only from the
 *  extractor. Always render it - a reduced answer presented as a full one is
 *  the failure this whole pipeline exists to prevent. */
export interface FullReview {
  stage: 'review'
  degraded: boolean
  degraded_reason?: string[]
  summary: string
  claims: ReviewClaim[]
  unstated?: string[]
  /** Same shape on the degraded path, where the questions are canned rather
   *  than generated - one renderer, not two. */
  missing: ReviewGap[]
  /** Present when some claims were dropped for failing verification. The
   *  response is still trustworthy - these are the ones that were not. */
  dropped_claims?: number
  cross_check?: {
    agreement_rate: number | null
    disagreements: string[]
    skipped?: string
  }
  model?: string
  llm_attempts?: number
  /** Client-side only: set when the API answered 429, as the seconds until
   *  the model's reading is available again. */
  retry_after?: number
}
