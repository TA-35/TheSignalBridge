// Claims from the Decode model that the page shouldn't show as they came.
//
// Checked on 144 real reviews (2026-10-13): the model sometimes files the
// sender's sign-off name under "Who" (8 of 24), quotes a phone extension or
// "a crazy week" as "By when" (8 of 32), and lists "let me know if you have
// any questions" as something to do. Each is dropped here, and a dropped Who
// or By when comes back as the question it should have been (ASK_INSTEAD).
import { deadlineWords } from './confirmBack'
import type { ReviewClaim, ReviewField } from '@/types/review'

// "Let me know if you have any questions", "feel free to call me": offers,
// not asks. "Let me know if you can make it" asks for an answer, so it stays.
const OFFER = [
  String.raw`feel free to`,
  String.raw`don['’]?t hesitate`,
  String.raw`happy to (?:help|chat|talk|discuss|answer)`,
  String.raw`(?:let me know|lmk) if (?:i|we) can (?:help|do anything|be of)`,
  // "mail me back if any questions", "get back to me if you have any queries"
  String.raw`(?:let me know|lmk|tell me|get back to me|(?:e-?)?mail me(?: back)?|call me|ping me|reach out)[^.!?\n]{0,30}?\bif\b[^.!?\n]{0,25}?\b(?:questions?|queries|concerns|doubts|issues|problems)`,
  // "if you have any questions, let me know"
  String.raw`if (?:you|u|there(?:['’]s| are| is)?)(?: have| got| need)? (?:any |more |further |other )?(?:questions?|queries|concerns)`,
  String.raw`any (?:other |further |more )?questions?,? (?:just |please )?(?:let me know|lmk|ask|shout|ping|call|email|mail|give me a (?:call|shout))`,
]
const COURTESY = new RegExp(String.raw`\b(?:${OFFER.join('|')})`, 'i')

// A reading that says the person is the sender, whatever name it gives.
const SENDER = new RegExp(
  String.raw`\b(?:[Tt]he sender is [A-Z]|is the sender|is the (?:person |one )?(?:sending|who sent|who initiated|requesting)|` +
    String.raw`(?:wrote|sent) (?:this|the) (?:message|email|note)|responsible for (?:requesting|sending|asking)|sign-?off|signed (?:off|the))`,
)

// The closing of a message: a short "Thanks," / "Cheers," style line, or a
// bare name as the last line. A name here is the sender's.
const CLOSING = /^[ \t]*(?:thanks|thank you|thx|many thanks|cheers|regards|kind regards|warm regards|best(?: regards| wishes)?|all the best|sincerely|yours|talk soon|speak soon|see you|ta)\b[^\n]*$/gim

/** Where the sign-off starts, or the message's length when there is none. */
export function signOffStart(message: string): number {
  let last = -1
  for (const m of message.matchAll(CLOSING)) {
    // "Thanks for sending the draft over, it looks great" opens a message;
    // a closing line is short.
    if (m[0].trim().split(/\s+/).length <= 6) last = m.index
  }
  if (last >= 0) return last
  const trimmed = message.trimEnd()
  const lines = trimmed.split('\n')
  const final = lines[lines.length - 1]?.trim() ?? ''
  if (lines.length >= 2 && final && final.split(/\s+/).length <= 3 && /^[A-Z]/.test(final) && !/[.!?]$/.test(final)) {
    return trimmed.length - final.length
  }
  return message.length
}

/** The sentence around a position in the message. */
function sentenceAt(message: string, at: number): string {
  const before = message.slice(0, Math.max(0, at))
  const start = Math.max(before.lastIndexOf('.'), before.lastIndexOf('!'), before.lastIndexOf('?'), before.lastIndexOf('\n')) + 1
  const rest = message.slice(Math.max(0, at))
  const stop = /[.!?\n]/.exec(rest)
  return message.slice(start, Math.max(0, at) + (stop ? stop.index : rest.length))
}

export interface FilteredClaims {
  claims: ReviewClaim[]
  /** Fields a claim was dropped from, so the page can ask about them instead. */
  dropped: ReviewField[]
}

// The sender's own next step, not the reader's: "call you in regards to the
// below email", "get back to you", "I'll send it over".
const SENDERS_STEP = /^(?:\S+(?:\s+(?:back|up|out|over|in))?(?:\s+(?:to|with|for))?\s+(?:you|u|ya)(?!['’\w])|(?:i|we)(?:['’]ll|\s+will|\s+am going to|\s+are going to|['’]m going to)\b)/i

/**
 * `otherAsks`: the extractor found something to do even if the model didn't.
 * With nothing to do at all, a "Who" or "By when" has nothing to belong to
 * ("the slides for Friday" read as a deadline), so those go too, and nothing
 * is asked about them.
 */
export function filterClaims(message: string, claims: readonly ReviewClaim[], otherAsks = false): FilteredClaims {
  const cut = signOffStart(message)
  const dropped: ReviewField[] = []
  const kept = claims.filter((claim) => {
    const at = claim.span?.[0] ?? message.indexOf(claim.text)
    let drop = false
    if (claim.field === 'required_action') {
      drop =
        COURTESY.test(claim.text) ||
        (at >= 0 && COURTESY.test(sentenceAt(message, at))) ||
        SENDERS_STEP.test(claim.text.trim())
    } else if (claim.field === 'responsible_person') {
      // Dropped when it is the sign-off name, a courtesy offer ("u can mail me
      // back if any questions"), or read by the model as the sender.
      drop =
        (at >= 0 && at >= cut) ||
        COURTESY.test(claim.text) ||
        (at >= 0 && COURTESY.test(sentenceAt(message, at))) ||
        SENDER.test(claim.reading ?? '')
    } else if (claim.field === 'deadline') {
      drop = deadlineWords(claim.text) === ''
    }
    if (drop) dropped.push(claim.field)
    return !drop
  })
  if (otherAsks || kept.some((c) => c.field === 'required_action')) return { claims: kept, dropped }
  const nothingToDo = new Set<ReviewField>(['responsible_person', 'deadline'])
  return {
    claims: kept.filter((c) => !nothingToDo.has(c.field)),
    dropped: dropped.filter((f) => !nothingToDo.has(f)),
  }
}

/** The question to ask when a claim about a field was dropped and the model listed no gap for it. */
export const ASK_INSTEAD: Partial<Record<ReviewField, string>> = {
  responsible_person: 'Who is meant to do this - me, or someone else?',
  deadline: 'When do you need this by?',
}
