// The "here's what I've got" lines a reader can open their reply with, so the
// sender can confirm or correct them before any work starts.
//
// Each ask the decoder found is the sender's own words ("send me the Q3
// report"), so it is turned round to the reader's side ("I'll send you the Q3
// report"). Only an ask that starts with a verb on the list below is turned
// round. Anything else (a question, a fragment, the sender's own promise) is
// left out, not quoted back. The review model's "what needs doing" quotes
// include things like "Link -->" and "Congrats on your promotion", and quoting
// those confirms nothing. The reply ends "Let me know if I've missed
// anything", which covers what was left out.

// Common verbs an ask starts with once "could you" and the like are gone.
const VERBS = new Set(
  `add answer approve arrange ask attach attend book bring build buy call cancel catch change chase check
  choose clarify clean clear collect come compile complete confirm contact copy cover create deal decide
  deliver deploy design do double-check draft drop edit elaborate email ensure expand explain file fill find
  finalise finalize finish fix follow forward gather get give go grab hand handle have help include insure
  invite join keep leave let list look make manage meet merge message move note order organise organize pass
  pay pick ping plan post prepare present print proofread provide push put read rebook record remind reply
  report request research reschedule respond return review ring run save schedule send set share sign sort
  speak start stop submit suggest summarise summarize swap take talk tell test text tidy tighten touch
  transfer update upload use write`.split(/\s+/),
)
// May come before the verb and stay in the line: "only edit those entries".
const ADVERB = new Set(['just', 'also', 'only', 'then', 'first', 'quickly'])

// "Hi Jordan, could you please" -> ""; "when you get a chance, can you" -> "".
// The model's quote can start part-way into the hedge: "get a chance could you
// maybe ..." -> "".
const LEAD = new RegExp(
  String.raw`^(?:(?:hi|hey|hello)\b[^,]*,\s*)?(?:(?:also|and|so|but),?\s+)?` +
    String.raw`(?:(?:(?:can|could|would|will)\s+(?:you|u)(?:\s+(?:please|pls|maybe|possibly|just))*|please|pls|plz|kindly|` +
    String.raw`(?:i|we)\s+need\s+you\s+to|need\s+you\s+to|(?:it\s+)?would\s+be\s+(?:great|good|nice|helpful|amazing)\s+if\s+you\s+could|` +
    String.raw`any\s+chance\s+you\s+could|are\s+you\s+able\s+to|(?:i\s+was\s+|just\s+)?wondering\s+if\s+you\s+could|` +
    String.raw`if\s+you\s+(?:can|could)|(?:when\s+you\s+)?(?:get\s+a\s+chance|have\s+a\s+(?:sec|second|minute|moment))|` +
    String.raw`when\s+you\s+(?:can|have\s+(?:a\s+)?(?:sec|second|minute|moment|time))),?\s+)*`,
  'i',
)
// The same lead-in part-way through, for a quote that starts mid-hedge:
// "get a chance could you maybe have a look at the slides".
const MID = /\b(?:(?:can|could|would|will)\s+(?:you|u)|please|pls|plz|kindly)\s+(?:(?:please|pls|maybe|possibly|just|quickly|also)\s+)*/gi
// "would you mind (possibly) updating the tracker" -> "update the tracker"
const MIND = /^(?:.*?\b)?(?:would|do|could)\s+(?:you|u)\s+mind\s+(?:(?:possibly|maybe|just|quickly)\s+)*/i
// "... the minutes please, thanks!" -> "... the minutes" (a whole word each: "rota" keeps its "ta")
const TRAIL = new RegExp(
  String.raw`(?:[\s,]+(?:please|pls|thanks|thank you|thx|ta|no rush|if possible|if you can|` +
    String.raw`if you (?:have|get) a (?:sec|second|minute|moment|chance)|when you (?:can|get a chance))\b)*[\s.!?]*$`,
  'i',
)

// The sender's own promise ("call you", "get back to you") is not the reader's
// to confirm. Turned round it would read "I'll call me".
const SENDERS = /^\S+(?:\s+(?:back|up|out|over|in))?(?:\s+(?:to|with|for))?\s+(?:you|u|ya)(?!['’\w])/i
// Pointers, not asks: "find attached", "see below".
const POINTER = /^(?:find|see)\s+(?:the\s+)?(?:attached|enclosed|below|above)\b/i
// A quote cut off mid-phrase ("figure out how to have", "mail me at the address or").
// Not "in" or "on": "log in" and "carry on" are whole.
const CUT = /\b(?:to|or|and|but|the|a|an|of|with|for|at|by|from|that|if|how|where|what|when|which|who|have|be|your|my|their|our)$/i
// A giving verb with its thing cut off: the extractor once stopped "send me
// the minutes from Tuesday" at "send me", and the reply read "I'll send you
// by 5pm tomorrow".
const NO_OBJECT = /^(?:send|give|forward|bring|pass|hand|show|lend|get|buy|find|grab|pick up)\s+(?:me|us|him|her|them)$/i

// The sender's side to the reader's.
const FLIP: Record<string, string> = {
  me: 'you', my: 'your', mine: 'yours', myself: 'yourself', i: 'you',
  "i'm": "you're", "i've": "you've", "i'll": "you'll", "i'd": "you'd",
  your: 'my', yours: 'mine', yourself: 'myself', ur: 'my', urs: 'mine',
  "you're": "I'm", "you've": "I've", "you'll": "I'll", "you'd": "I'd",
}
// "you" is the reader's "I" when it does something ("if you have time", "as
// soon as you can"), and their "me" otherwise ("send it to you").
const SUBJECT_NEXT = new RegExp(
  String.raw`^(?:are|were|was|have|had|has|can|could|will|would|shall|should|may|might|must|need|needs|want|wanted|` +
    String.raw`get|got|think|thought|know|knew|see|saw|said|say|mentioned|mean|meant|do|did|does|go|went|feel|felt|` +
    String.raw`agree|already|also|just|still|really|cannot|(?:can|won|wouldn|couldn|shouldn|don|didn|doesn|haven|aren|weren)['’]t)\b`,
  'i',
)
const SUBJECT_AFTER = /\b(?:if|when|whether|as|that|so|because|unless|until|once|while|where|what|how|why|which|who|than)\s*$/i
// Longest first, so "you're" isn't read as "you" followed by "'re".
const PRONOUN = /\b(?:you['’](?:re|ve|ll|d)|yourself|yours|your|you|urs|ur|u|i['’](?:m|ve|ll|d)|myself|mine|my|me|i)\b/gi
// Turning "I" into "you" and back breaks the verb that follows: "how wrong I was".
const AGREE: [RegExp, string][] = [
  [/\byou was\b/g, 'you were'],
  [/\bI were\b/g, 'I was'],
  [/\bI are\b/g, 'I am'],
  [/\byou am\b/g, 'you are'],
]

function flip(text: string): string {
  const flipped = text.replace(PRONOUN, (word, at: number, whole: string) => {
    const key = word.toLowerCase().replace('’', "'")
    if (key === 'you' || key === 'u') {
      const subject =
        SUBJECT_NEXT.test(whole.slice(at + word.length).trimStart()) || SUBJECT_AFTER.test(whole.slice(0, at))
      return subject ? 'I' : 'me'
    }
    return FLIP[key] ?? word
  })
  return AGREE.reduce((out, [wrong, right]) => out.replace(wrong, right), flipped)
}

const bare = (word = '') => word.toLowerCase().replace(/[^a-z-]/g, '')

function startsWithVerb(text: string): boolean {
  const [first, second] = text.split(/\s+/)
  return VERBS.has(bare(first)) || (ADVERB.has(bare(first)) && VERBS.has(bare(second)))
}

// "updating" -> "update", "putting" -> "put", if it's on the list.
function baseForm(word: string): string | null {
  const w = bare(word)
  if (!w.endsWith('ing')) return null
  const stem = w.slice(0, -3)
  return [stem, `${stem}e`, stem.replace(/(.)\1$/, '$1')].find((v) => VERBS.has(v)) ?? null
}

function balanced(text: string): boolean {
  const count = (re: RegExp) => (text.match(re) ?? []).length
  return count(/\(/g) === count(/\)/g) && count(/"/g) % 2 === 0 && count(/“/g) === count(/”/g)
}

/**
 * One ask as the reader would confirm it, "I'll send you the Q3 report by
 * Friday", or null when it can't be turned round safely.
 */
export function confirmLine(ask: string, detail = ''): string | null {
  let core = ask.trim()
  const mind = core.match(MIND)
  if (mind) {
    const rest = core.slice(mind[0].length)
    const first = rest.split(/\s+/)[0] ?? ''
    const base = baseForm(first)
    if (!base) return null
    core = base + rest.slice(first.length)
  }
  core = core.replace(LEAD, '').replace(TRAIL, '')
  if (!startsWithVerb(core)) {
    let cut = -1
    for (const m of core.matchAll(MID)) {
      const end = m.index + m[0].length
      if (startsWithVerb(core.slice(end))) cut = end
    }
    if (cut < 0) return null
    core = core.slice(cut).replace(TRAIL, '')
  }
  if (SENDERS.test(core) || POINTER.test(core) || CUT.test(core) || NO_OBJECT.test(core) || !balanced(core)) return null

  const [first = '', ...rest] = core.split(/\s+/)
  // "CALL A&K" -> "call A&K", "Send" -> "send"
  const opening = first.length > 1 && first === first.toUpperCase() ? first.toLowerCase() : first.charAt(0).toLowerCase() + first.slice(1)
  const lower = [opening, ...rest].join(' ')
  // A deadline already in the ask isn't repeated: "by Friday by Friday".
  const tail = detail && !lower.toLowerCase().includes(detail.toLowerCase()) ? ` ${detail}` : ''
  return `I'll ${flip(lower + tail)}`
}

/** "by Friday · for me" from the decoder -> "by Friday, for me" (turned round by confirmLine). */
export function detailWords(detail: string): string {
  // The extractor can put one word in two slots ("for Tuesday · at Tuesday"); say it once.
  const seen = new Set<string>()
  return detail
    .split(' · ')
    .filter((part) => {
      const value = part.replace(/^\S+\s+/, '').toLowerCase()
      if (!part || seen.has(value)) return false
      seen.add(value)
      return true
    })
    .join(', ')
}

// Whole names and short forms: "Wednesday" is wed + nes + day, "Saturday" sat + ur + day.
const DAYS = String.raw`(?:mon|tues?|wed(?:nes|s)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)(?:day)?(?:['’]s)?`
const MONTHS = String.raw`(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?`
// A month on its own ("until July"); not "may", which is usually the verb.
const BARE_MONTH = String.raw`(?:jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*`
// Reads as a time: "Friday", "3pm", "the 13th", "end of day", "next week", "in 2 hours".
const TIME = new RegExp(
  String.raw`^(?:(?:about|around|roughly)\s+)?(?:the\s+)?(?:` +
    String.raw`\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.?|p\.m\.?)|\d{1,2}(?:st|nd|rd|th)|\d{1,2}[/.-]\d{1,2}|` +
    String.raw`\d+\s+(?:min(?:ute)?s?|hours?|hrs?|days?|weeks?)|today|tonight|tomorrow|tmrw|eod|eow|cob|noon|midday|` +
    String.raw`lunch(?:time)?|morning|afternoon|evening|(?:end|close)\s+of|first\s+thing|` +
    String.raw`(?:this|next)\s+(?:week(?:end)?|month|quarter|year|morning|afternoon|evening|${DAYS})|` +
    String.raw`${DAYS}|${MONTHS}\s+\d|\d{1,2}\s+${MONTHS}|${BARE_MONTH}|hour|day|week)(?![a-z\d])`,
  'i',
)
const RELATION = /^(?:by|before|on|until|till|at|in|within|for|no\s+later\s+than)\s+/i
const AS_IS = /^(?:today|tonight|tomorrow|tmrw|this|next|first\s+thing)\b/i
// A time then a thing ("3pm review tomorrow") is an event to be ready before.
const EVENT = /^(?:\S+\s+){1,2}(?:meeting|mtg|review|call|sync|standup|stand-up|demo|presentation|session|catch-?up|check-?in|interview|briefing|workshop|launch)\b/i

/**
 * The model's deadline quote as words that can follow an ask ("by Friday",
 * "before the 3pm review"), or '' when it doesn't read as a time. The quote is
 * sometimes a phone extension or "hours from last week", and "I'll call by
 * x6-6002" is worse than leaving the deadline to the questions.
 */
export function deadlineWords(deadline: string): string {
  const d = deadline.trim().replace(/[\s,;:!?]+$/, '').replace(/(?<!\b[ap]\.m)\.$/i, '')
  if (/^(?:asap|as soon as possible)$/i.test(d)) return 'as soon as possible'
  const rest = d.replace(RELATION, '')
  if (!TIME.test(rest)) return ''
  if (rest !== d) return d
  if (EVENT.test(d)) return /^\S+['’]s\s/.test(d) ? `before ${d}` : `before the ${d}`
  return AS_IS.test(d) ? d : `by ${d}`
}
