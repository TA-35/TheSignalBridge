// What a sender's draft leaves a literal reader to guess, and how the sender
// fills it in. Only the sender knows these answers, and the rewriter may not
// invent them (the grounding check rejects any fact the draft doesn't
// contain), so the page asks, puts the answers into the draft, and rewrites.
//
// Every check needs a signal that holds up on real drafts: the rewrite model's
// own reading for the deadline, and the draft's own words for the rest.
// Decode's extractors are not used - on drafts they flag "by 3pm Thursday" as
// a missing time and find a missing purpose in nearly everything.
//
// An answer that settles words already in the draft replaces them ("Can
// someone" -> "Can Sam"; "No rush, but" goes once it is urgent). Left in, the
// model keeps both and the message contradicts itself: "No rush ... This is
// urgent." Anything else goes in as one plain sentence.
import { addToDraft, deadlineSentence, QUICK_DEADLINES } from './deadline'

export type MissingKey = 'when' | 'who' | 'what' | 'urgency'

export interface QuickAnswer {
  label: string
  sentence: string
}

/** One answer: the index of a quick choice, or typed words. */
export interface Answer {
  quick: number | null
  typed: string
}

export interface MissingItem {
  key: MissingKey
  question: string
  quick: readonly QuickAnswer[]
  /** Placeholder for a typed answer; empty means quick answers only. */
  placeholder: string
  /** A typed answer as one sentence for the draft ('' if it is empty). */
  sentence: (typed: string) => string
  /** Changes the draft's own words where the answer settles them; `done`
   *  means the sentence isn't needed as well. */
  settle?: (draft: string, answer: Answer) => { draft: string; done: boolean }
}

// The task is handed to no one in particular: "can someone", "whoever".
// "If anyone has questions" is not a task, so a bare "anyone" doesn't count.
const UNASSIGNED =
  /\b(?:can|could|would|will)\s+(?:some(?:one|body)|any(?:one|body)|one of you)\b|\bsome(?:one|body)\s+(?:needs? to|should|has to|must)\b|\bwhoever\b|\bif\s+any(?:one|body)\s+(?:can|could|has time|is free)\b/i

// A verb that says something should happen without saying what.
const VAGUE =
  /\b(?:take|have|give it) a (?:quick )?(?:look|pass)(?: at| over)?|\blook (?:into|over)\b|\b(?:tighten|clean|touch|smarten) (?:it |this |that )?up\b|\bsort (?:it |this |that )?out\b|\bpolish (?:it|this|that) up\b/i

// Softeners that a literal reader can take as "optional". A subset of the
// canonical hedge list in Src/source/model/tone/enron_step1.py.
const HEDGE_WORDS = String.raw`no rush|no pressure|no hurry|whenever you (?:can|get a chance)|when(?:ever)? you (?:get|have) a (?:chance|minute|moment|sec)|if you (?:get|have) a (?:chance|minute|moment|sec)|if you have (?:the )?time|at some point`
const HEDGE = new RegExp(String.raw`\b(?:${HEDGE_WORDS})\b`, 'i')

const URGENCY_ANSWERS = [
  { label: 'Urgent', sentence: 'This is urgent.' },
  { label: 'Needed, not urgent', sentence: "It isn't urgent, but I do need it done." },
  { label: 'Truly optional', sentence: 'This is optional, only if you have time.' },
] as const
const TRULY_OPTIONAL = 2 // the hedge is true then, so it stays

const plain = (text: string) => text.trim().replace(/[\s.!]+$/, '')
const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)

/** Takes "no rush" and the like out: "No rush, but could you..." -> "Could you...". */
export function dropHedges(draft: string): string {
  const h = String.raw`(?:${HEDGE_WORDS})(?:\s+(?:though|then))?`
  const start = String.raw`(^|[.!?]\s+|\n\s*)`
  return (
    draft
      // a sentence of its own: "No pressure though!"
      .replace(new RegExp(String.raw`${start}${h}\s*[.!?]+[ \t]*`, 'gi'), '$1')
      // opening the sentence that asks: "When you get a chance, could you"
      .replace(new RegExp(String.raw`${start}${h}\s*(?:[,;:-]\s*(?:but\s+)?|\s+but\s+)(\w)`, 'gi'),
        (_m, lead: string, c: string) => lead + c.toUpperCase())
      // set off by commas inside the sentence: "Could you, if you get a chance, check it"
      .replace(new RegExp(String.raw`,\s*${h}\s*,`, 'gi'), '')
      // closing the sentence: "check it when you get a chance?"
      .replace(new RegExp(String.raw`,?\s+${h}(?=\s*[.!?,]|\s*$)`, 'gi'), '')
      .replace(/[ \t]+$/gm, '')
  )
}

/** Gives the task to `who` ("you" or a name): "Can someone" -> "Can Sam". */
export function assignTo(draft: string, who: string): string {
  const you = who === 'you'
  return draft
    .replace(/\b(can|could|would|will)\s+(?:some(?:one|body)|any(?:one|body)|one of you)\b/gi,
      (_m, modal: string) => `${modal} ${who}`)
    .replace(/\b(some(?:one|body))\s+(needs? to|should|has to|must)\b/gi, (_m, subject: string, verb: string) => {
      const doer = subject.charAt(0) === subject.charAt(0).toUpperCase() ? capital(who) : who
      const agreed = you ? verb.replace(/^needs/i, 'need').replace(/^has to/i, 'have to') : verb
      return `${doer} ${agreed}`
    })
    .replace(/(^|[.!?]\s+|\n\s*|,\s+)whoever\s+(?:is\s+(?:free|available|around)|can|has (?:the )?time)\s*,\s*(\w)/gi,
      (_m, lead: string, c: string) => {
        const opens = !lead.startsWith(',')
        if (you) return lead + (opens ? c.toUpperCase() : c)
        return `${lead}${opens ? capital(who) : who}, ${c}`
      })
}

/** What the draft leaves out, given the rewrite model's reading of it. */
export function findMissing(draft: string, meaning: { ask: string; deadline: string }): MissingItem[] {
  // An update or a thank-you asks nothing, so it owes the reader none of this.
  if (!meaning.ask.trim()) return []
  const items: MissingItem[] = []

  if (!meaning.deadline.trim()) {
    items.push({
      key: 'when',
      question: 'When do you need it?',
      quick: QUICK_DEADLINES,
      placeholder: '3pm Friday',
      sentence: deadlineSentence,
    })
  }

  if (UNASSIGNED.test(draft)) {
    const whoOf = (answer: Answer) => (answer.quick !== null ? 'you' : plain(answer.typed))
    items.push({
      key: 'who',
      question: 'Who should do it?',
      quick: [{ label: 'The person I send this to', sentence: "I'm asking you to do this." }],
      placeholder: 'A name, such as Sam',
      sentence: (typed) => (plain(typed) ? `I'm asking ${plain(typed)} to do this.` : ''),
      settle: (text, answer) => {
        const changed = assignTo(text, whoOf(answer))
        return { draft: changed, done: changed !== text }
      },
    })
  }

  const vague = VAGUE.exec(draft)
  if (vague) {
    items.push({
      key: 'what',
      question: `What exactly do you mean by “${vague[0].toLowerCase()}”?`,
      quick: [],
      placeholder: 'Fix the totals in the numbers section',
      sentence: (typed) => (plain(typed) ? `To be specific: ${plain(typed)}.` : ''),
    })
  }

  if (HEDGE.test(draft)) {
    items.push({
      key: 'urgency',
      question: 'How urgent is it, really?',
      quick: URGENCY_ANSWERS,
      placeholder: '',
      sentence: () => '',
      settle: (text, answer) => ({
        draft: answer.quick === TRULY_OPTIONAL ? text : dropHedges(text),
        done: false,
      }),
    })
  }
  return items
}

/** The draft with the sender's answers in it, ready to rewrite. */
export function applyAnswers(
  draft: string,
  items: MissingItem[],
  answers: Partial<Record<MissingKey, Answer>>,
): string {
  let text = draft
  const sentences: string[] = []
  for (const item of items) {
    const answer = answers[item.key]
    if (!answer) continue
    const sentence = answer.quick !== null ? (item.quick[answer.quick]?.sentence ?? '') : item.sentence(answer.typed)
    if (!sentence) continue
    const settled = item.settle?.(text, answer) ?? { draft: text, done: false }
    text = settled.draft
    if (!settled.done) sentences.push(sentence)
  }
  return sentences.length ? addToDraft(text, sentences.join(' ')) : text
}
