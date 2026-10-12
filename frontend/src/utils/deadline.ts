// The deadline a sender adds to their draft when the rewrite found an ask but
// no deadline. The rewriter can't add one itself: the grounding check rejects
// any date the draft doesn't contain. So the sender picks or types it, it goes
// into the draft as one plain sentence, and the draft is rewritten again.

export const QUICK_DEADLINES = [
  { label: 'Today', sentence: 'I need this by the end of today.' },
  { label: 'Tomorrow', sentence: 'I need this by tomorrow.' },
  { label: 'This week', sentence: 'I need this by the end of this week.' },
  // Saying there is none is as useful to a literal reader as a date.
  { label: 'No deadline', sentence: "There's no deadline for this." },
] as const

// "3pm Friday" -> "I need this by 3pm Friday." Words that already say how the
// time relates ("before the meeting", "on Monday") are kept as typed.
export function deadlineSentence(typed: string): string {
  const when = typed.trim().replace(/[\s.!]+$/, '')
  if (!when) return ''
  if (/^(asap|as soon as possible)$/i.test(when)) return 'I need this as soon as possible.'
  const lead = /^(today|tomorrow|tonight|this|next|end)\b/i.test(when) ? when.charAt(0).toLowerCase() + when.slice(1) : when
  return /^(by|before|on|at|until|till|within|in|no later than)\b/i.test(lead)
    ? `I need this ${lead}.`
    : `I need this by ${lead}.`
}

// Goes in before a short closing paragraph ("Thanks!", "Cheers, Sam"), so the
// draft still reads naturally if they keep their own version; otherwise at the end.
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
  return `${text}\n\n${sentence}`
}
