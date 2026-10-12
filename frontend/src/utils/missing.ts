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
// Answers change the draft's own words wherever they can, rather than adding
// to them. The model treats a draft that already states things as clear and
// keeps it as written, so an answer tacked on after a vague sentence stays
// tacked on ("To be specific: ..."), and a softener left beside "This is
// urgent." contradicts it. The vague sentence is rewritten by the sender
// themselves; "Can someone" becomes "Can Sam"; "would be great to have it"
// becomes "I need it". Only what has no words in the draft yet - a deadline -
// goes in as a new sentence.
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
  /** Placeholder for a typed answer; empty means no typed answer. */
  placeholder: string
  /** Text to edit in place, when the answer is a rewrite of the draft's own sentence. */
  prefill?: string
  /** A typed answer as one sentence to add ('' if it adds none). */
  sentence: (typed: string) => string
  /** Whether this answer says anything (default: a quick choice, or a typed sentence). */
  answered?: (answer: Answer) => boolean
  /** Changes the draft's own words; `done` means no sentence is added as well. */
  settle?: (draft: string, answer: Answer) => { draft: string; done: boolean }
}

// The task is handed to no one in particular: "can someone", "whoever".
// "If anyone has questions" is not a task, so a bare "anyone" doesn't count.
const UNASSIGNED =
  /\b(?:can|could|would|will)\s+(?:some(?:one|body)|any(?:one|body)|one of you)\b|\bsome(?:one|body)\s+(?:needs? to|should|has to|must)\b|\bwhoever\b|\bif\s+any(?:one|body)\s+(?:can|could|has time|is free)\b/i

// A verb that says something should happen without saying what.
const VAGUE =
  /\b(?:take|have|give it) a (?:quick )?(?:look|pass)(?: at| over)?|\blook (?:into|over)\b|\b(?:tighten|clean|touch|smarten) (?:it |this |that )?up\b|\bsort (?:it |this |that )?out\b|\bpolish (?:it|this|that) up\b/i

// Softeners a literal reader can take as "optional", from the canonical hedge
// list (Src/source/data_prep/flag_rule.py). HEDGE_WORDS can be cut out of a
// sentence whole; a SOFTENER carries the sentence, so it is reworded instead.
const HEDGE_WORDS = String.raw`no rush|no pressure|no hurry|not urgent|whenever you (?:can|get a chance)|when(?:ever)? you (?:get|have) a (?:chance|minute|moment|sec)|if you (?:get|have) a (?:chance|minute|moment|sec)|if you have (?:the )?time|at your convenience|at some point`
const HEDGE = new RegExp(String.raw`\b(?:${HEDGE_WORDS})\b`, 'i')
const SOFT = String.raw`(?:it )?would be (?:great|nice|good|ideal|helpful)`
const SOFTENER = new RegExp(String.raw`\b${SOFT} (?:to have (?:it|this|them|that)|if you could)\b`, 'i')

const URGENCY_ANSWERS = [
  { label: 'Urgent', sentence: 'This is urgent.' },
  { label: 'Needed, not urgent', sentence: "It isn't urgent, but I do need it done." },
  { label: 'Truly optional', sentence: 'This is optional, only if you have time.' },
] as const
const TRULY_OPTIONAL = 2 // the softeners are true then, so they stay

// A rewritten sentence shorter than this isn't saying what is needed ("file").
const MIN_WORDS = 4

const plain = (text: string) => text.trim().replace(/[\s.!]+$/, '')
const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)
const words = (text: string) => text.trim().split(/\s+/).filter(Boolean).length
const START = String.raw`(^|[.!?]\s+|\n\s*)`

/** Takes "no rush" and the like out: "No rush, but could you..." -> "Could you...". */
export function dropHedges(draft: string): string {
  const h = String.raw`(?:${HEDGE_WORDS})(?:\s+(?:though|then))?`
  return (
    draft
      // a sentence of its own: "No pressure though!"
      .replace(new RegExp(String.raw`${START}${h}\s*[.!?]+[ \t]*`, 'gi'), '$1')
      // opening the sentence that asks: "When you get a chance, could you"
      .replace(new RegExp(String.raw`${START}${h}\s*(?:[,;:-]\s*(?:but\s+)?|\s+but\s+)(\w)`, 'gi'),
        (_m, lead: string, c: string) => lead + c.toUpperCase())
      // set off by commas inside the sentence: "Could you, if you get a chance, check it"
      .replace(new RegExp(String.raw`,\s*${h}\s*,`, 'gi'), '')
      // closing the sentence: "check it when you get a chance?"
      .replace(new RegExp(String.raw`,?\s+${h}(?=\s*[.!?,]|\s*$)`, 'gi'), '')
      .replace(/[ \t]+$/gm, '')
  )
}

/** "Would be great to have it" -> "I need it"; "it would be great if you could send" -> "please send". */
export function firmUp(draft: string): string {
  return draft
    .replace(new RegExp(String.raw`${START}${SOFT} to have (it|this|them|that)\b`, 'gi'),
      (_m, lead: string, what: string) => `${lead}I need ${what}`)
    .replace(new RegExp(String.raw`\b${SOFT} to have (it|this|them|that)\b`, 'gi'), (_m, what: string) => `I need ${what}`)
    .replace(new RegExp(String.raw`${START}${SOFT} if you could\s+`, 'gi'), (_m, lead: string) => `${lead}Please `)
    .replace(new RegExp(String.raw`\b${SOFT} if you could\s+`, 'gi'), 'please ')
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

/** The sentence around `index`, as it stands in the draft. */
export function sentenceAt(draft: string, index: number): string {
  const before = draft.slice(0, index)
  const start = Math.max(before.search(/[^.!?\n]*$/), 0)
  const end = draft.slice(index).search(/[.!?](?=\s|$)|\n/)
  const stop = end === -1 ? draft.length : index + end + (/[.!?]/.test(draft.charAt(index + end)) ? 1 : 0)
  return draft.slice(start, stop).trim()
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
    const original = sentenceAt(draft, vague.index)
    items.push({
      key: 'what',
      question: `“${vague[0].toLowerCase()}” could mean a lot of things. Rewrite this sentence to say exactly what you need:`,
      quick: [],
      placeholder: '',
      prefill: original,
      sentence: () => '',
      answered: (answer) =>
        words(answer.typed) >= MIN_WORDS && plain(answer.typed).toLowerCase() !== plain(original).toLowerCase(),
      settle: (text, answer) => {
        const rewritten = answer.typed.trim().replace(/[^.!?]$/, (c) => `${c}.`)
        return { draft: text.includes(original) ? text.replace(original, rewritten) : text, done: true }
      },
    })
  }

  if (HEDGE.test(draft) || SOFTENER.test(draft)) {
    items.push({
      key: 'urgency',
      question: 'How urgent is it, really?',
      quick: URGENCY_ANSWERS,
      placeholder: '',
      sentence: () => '',
      settle: (text, answer) => ({
        draft: answer.quick === TRULY_OPTIONAL ? text : dropHedges(firmUp(text)),
        done: false,
      }),
    })
  }
  return items
}

/** Whether an answer to `item` says anything. */
export function isAnswered(item: MissingItem, answer: Answer | undefined): boolean {
  if (!answer) return false
  return item.answered ? item.answered(answer) : answer.quick !== null || !!item.sentence(answer.typed)
}

// The sentence rewrite goes first: the other answers change words inside it
// ("Can someone" -> "Can Sam"), and it has to be found as the sender saw it.
const SETTLE_ORDER: MissingKey[] = ['what', 'who', 'urgency', 'when']

/** The draft with the sender's answers in it, ready to rewrite. */
export function applyAnswers(
  draft: string,
  items: MissingItem[],
  answers: Partial<Record<MissingKey, Answer>>,
): string {
  let text = draft
  const added: { key: MissingKey; sentence: string }[] = []
  const ordered = [...items].sort((a, b) => SETTLE_ORDER.indexOf(a.key) - SETTLE_ORDER.indexOf(b.key))
  for (const item of ordered) {
    const answer = answers[item.key]
    if (!answer || !isAnswered(item, answer)) continue
    const settled = item.settle?.(text, answer) ?? { draft: text, done: false }
    text = settled.draft
    if (settled.done) continue
    const sentence = answer.quick !== null ? (item.quick[answer.quick]?.sentence ?? '') : item.sentence(answer.typed)
    if (sentence) added.push({ key: item.key, sentence })
  }
  // Added in the order the questions were asked, not the order they were settled in.
  const asked = items.map((item) => item.key)
  added.sort((a, b) => asked.indexOf(a.key) - asked.indexOf(b.key))
  return added.length ? addToDraft(text, added.map((a) => a.sentence).join(' ')) : text
}
