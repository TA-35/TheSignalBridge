// The deadline a sender adds to their draft when the rewrite found an ask with
// no deadline, or only a loose one ("sometime soon"). The rewriter can't add
// one itself: the grounding check rejects any date the draft doesn't contain.
// So the sender picks or types it, it goes into the draft - in place of the
// loose words where there are some, else as one plain sentence - and the
// draft is rewritten again.

export const QUICK_DEADLINES = [
  { label: 'Today', phrase: 'by the end of today' },
  { label: 'Tomorrow', phrase: 'by tomorrow' },
  { label: 'This week', phrase: 'by the end of this week' },
  // Saying there is none is as useful to a literal reader as a date.
  { label: 'No deadline', phrase: '' },
] as const

// "3pm Friday" -> "by 3pm Friday". Words that already say how the time relates
// ("before the meeting", "on Monday", "tonight b4 9") are kept as typed.
export function deadlinePhrase(typed: string): string {
  const when = typed
    .trim()
    .replace(/[\s.!]+$/, '')
    .replace(/\bb4\b/gi, 'before')
  if (!when) return ''
  if (/^(asap|as soon as possible)$/i.test(when)) return 'as soon as possible'
  const lead = /^(today|tomorrow|tonight|this|next|end)\b/i.test(when) ? when.charAt(0).toLowerCase() + when.slice(1) : when
  return /^(by|before|on|at|until|till|within|in|no later than)\b/i.test(lead) || /\b(before|by|until|till)\b/i.test(lead)
    ? lead
    : `by ${lead}`
}

// A sign-off at the end of the last line itself: "...for 12 people? Ta".
const SIGN_OFF =
  /[.!?](?=\s+(?:thanks|thank you|thx|thnx|ty|ta|cheers|xx?x?|love|best|regards|many thanks|tysm)\b[^.!?\n]{0,24}[.!]*[^\w\n]*$)/i

// Goes in before a short closing paragraph ("Thanks!", "Cheers, Sam") or a
// sign-off ending the last line, so the draft still reads naturally if they
// keep their own version; otherwise at the end.
export function addToDraft(draft: string, sentence: string): string {
  const text = draft.trimEnd()
  const breaks = [...text.matchAll(/\n\s*\n/g)]
  const last = breaks[breaks.length - 1]
  if (last?.index !== undefined) {
    const closing = text.slice(last.index + last[0].length)
    if (closing.split(/\s+/).filter(Boolean).length <= 4) {
      return `${text.slice(0, last.index)}\n\n${sentence}${text.slice(last.index)}`
    }
  }
  const sign = SIGN_OFF.exec(text)
  if (sign) return `${text.slice(0, sign.index + 1)} ${sentence}${text.slice(sign.index + 1)}`
  return `${text}\n\n${sentence}`
}
