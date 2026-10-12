// What a sender's draft leaves a literal reader to guess, and how the sender
// fills it in. Only the sender knows these answers, and the rewriter may not
// invent them (the grounding check rejects any fact the draft doesn't
// contain), so the page asks, puts the answers into the draft, and rewrites.
//
// Every check needs a signal that holds up on real drafts: the rewrite model's
// own reading for the ask and the deadline, and the draft's own words for the
// rest. Decode's extractors are not used - on drafts they flag "by 3pm
// Thursday" as a missing time and find a missing purpose in nearly everything.
//
// Answers change the draft's own words wherever they can, rather than adding
// to them. The model treats a draft that already states things as clear and
// keeps it as written, so an answer tacked on after a vague sentence stays
// tacked on ("To be specific: ..."), and a softener left beside "This is
// urgent." contradicts it. The vague sentence is rewritten by the sender
// themselves; "Can someone" becomes "Sam, can you"; "when you get a chance"
// becomes "by Friday"; "would be great to have it" becomes "I need it". Only
// what has no words in the draft yet goes in as a new sentence.
//
// The word lists and the cases each check stays quiet on come from 100
// everyday drafts (work asks, plans, group chats, non-asks, texting) run
// through the live model and judged one by one on 2026-10-12.
import { addToDraft, deadlinePhrase, QUICK_DEADLINES } from './deadline'

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
  /** The card's title when this is the only question (default: one per key). */
  title?: string
  question: string
  quick: readonly QuickAnswer[]
  /** Placeholder for a typed answer; empty means no typed answer. */
  placeholder: string
  /** Text to edit in place, when the answer is a rewrite of the draft's own sentence. */
  prefill?: string
  /** What a good rewrite of `prefill` looks like. */
  hint?: string
  /** A typed answer as one sentence to add ('' if it adds none). */
  sentence: (typed: string) => string
  /** Whether this answer says anything (default: a quick choice, or a typed sentence). */
  answered?: (answer: Answer) => boolean
  /** Changes the draft's own words; `done` means no sentence is added as well. */
  settle?: (draft: string, answer: Answer) => { draft: string; done: boolean }
}

interface Meaning {
  ask: string
  deadline: string
}

// ---- The words the checks look for

const AP = `['’]` // apostrophes, straight or curly as phones type them
const YOU = String.raw`(?:you|u|ya)`
// A doer nobody is named as: "someone", "anyone", "one of you", texting forms too.
const NOBODY = String.raw`(?:some(?:one|body)|sum1|some1|any(?:one|body)|any1|(?:one|either|any) of (?:you|u|ya)(?: (?:guys|all|two|lot))?)`

// A greeting, the name of whoever is spoken to, or a linking word ahead of the
// sentence proper: "Hey Sam, ", "Morning all! ", "Dad, ", "Also, ".
const GREETING = String.raw`(?:hi|hey|hiya|hello|morning|evening|afternoon|good (?:morning|afternoon|evening)|dear|yo)`
const OPENER = String.raw`(?:${GREETING}(?:[ \t]+(?:all|everyone|guys|team|folks|both|you two))?[ \t]*[,!]?[ \t]+|(?:${GREETING}[ \t]+)?[\w'’-]+(?: and [\w'’-]+)?,[ \t]+|(?:also|and|so|plus|btw|ok|okay|oh)\b,?[ \t]+)`
const START = String.raw`(^|[.!?]\s+|\n\s*)`
// The text before a position ends at the start of a sentence, perhaps after an opener.
const OPENS = new RegExp(String.raw`(?:^|[.!?]\s+|\n\s*)(?:${OPENER})*$`, 'i')
const BARE_START = /^(?:[.!?]\s+|\n\s*)?$/

// Softeners a literal reader can take as "optional", from the canonical hedge
// list (Src/source/data_prep/flag_rule.py) and the drafts above. Loose time
// words are replaced by the deadline the sender gives; "no rush" words say how
// soon; "maybe" words say whether at all. A SOFT phrase carries its sentence,
// so it is reworded rather than cut.
// ("at some point this morning they were removed" is the past, not a hedge;
// "arriving sometime before noon" has its time)
const LOOSE_PHRASE = String.raw`when(?:ever|evr|eva)? ${YOU} (?:get|have|got|find) (?:a|the) (?:chance|minute|min|moment|mo|sec|second)|when(?:ever|evr)? ${YOU} can|if ${YOU} (?:get|have|find) (?:a|the) (?:chance|minute|min|moment|sec|second)|at (?:some|any) point(?! (?:this morning|yesterday|last|earlier|overnight)\b)|at (?:your|ur) (?:earliest )?convenience|back at the earliest`
const LOOSE_WORD = String.raw`(?:some ?time )?soon(?:ish)?|some ?time(?! (?:before|after|between|by|around|on|today|tonight|tomorrow)\b)(?: (?:this|next) (?:week|month|weekend))?|later(?! (?:in|this|next|on)\b)(?: today| on)?|in a (?:bit|while)|whenever(?: works)?`
const LOOSE_TIME = new RegExp(String.raw`\b(?:${LOOSE_PHRASE}|${LOOSE_WORD})\b`, 'i')
const LOOSE_DEADLINE = new RegExp(String.raw`\b(?:${LOOSE_PHRASE}|${LOOSE_WORD}|eventually)\b`, 'i')
// "No rush on your timesheet" is about something else, so it doesn't count.
const RUSH = String.raw`no (?:(?:huge|big|real|great|mad|massive) )?(?:rush|hurry)(?!\s+(?:on|with|for)\s+(?!(?:this|that|it)\b))|not (?:(?:super|too|that|very|really) )?urgent`
const MAYBE = String.raw`no pressure|no worries if (?:not|${YOU} can${AP}?t)|if ${YOU} have (?:the )?time(?!\s+for\b)|if ${YOU}(?:${AP}ve| have) got (?:the )?time|if ${YOU}(?:${AP}re| are|r) free|if possible|if ${YOU} can(?=\s*(?:[.!?,]|$))`
const HEDGE_WORDS = `${RUSH}|${MAYBE}|${LOOSE_PHRASE}`
const SOFT = String.raw`(?:(?:it|that)(?:${AP}d| would)|would|wud|${AP}d) be (?:(?:really|so|super|very) )?(?:great|nice|good|ideal|helpful|amazing|awesome|lovely|brilliant|perfect|gr8|fab|fantastic|handy)`
const SOFTENER = new RegExp(String.raw`\b${SOFT}(?: (?:to have (?:it|this|them|that)|if (?:${YOU}|${NOBODY}) (?:could|can)|before|by)\b|(?=\s*(?:[,.!?]|[^\w\s]*\s*$)))|\bshould probably\b`, 'i')
// "Let me know if you can" asks whether, so the "if" there is no hedge.
const ASKS_WHETHER = /\b(?:know|lmk|ask|tell me|see|whether)\s*$/i
// The sender has already said it's fine if nobody does it ("otherwise just
// bring yourselves"), not just that another time is ("otherwise after lunch is fine").
const FINE_IF_NOT =
  /\b(?:otherwise|if not|or not),?\s+(?:(?:that|it)['’]?s\s+|no\s+)?(?:totally\s+|completely\s+)?(?:fine|ok|okay|all good|worries|stress|problem|just bring)\b|\b(?:totally|completely|perfectly|all) (?:fine|good|ok) if not\b/i

// The task handed to no one in particular. Asked of whoever reads it:
const MODAL = String.raw`\b(can|could|would|will|cud|cn)\s+(${NOBODY})((?:\s+(?:on|from|in) (?:your|the|our) (?:team|group|side|end|lot|crew))?)\b`
const IF_ANYONE = String.raw`\bif\s+(${NOBODY})\s+(can|could|is (?:free|around|able|available)|has (?:the )?time|gets? a chance|wants? to)\b`
const ANYONE_FREE = String.raw`\bany(?:one|body|1)\s+(free|able|around|available|keen)\s+to\b`
const ANY_VOLUNTEERS = String.raw`\bany (?:volunteers|takers)\b`
const WHOEVER = String.raw`whoever(?:${AP}s|\s+is|\s+are|\s+gets|\s+can|\s+has(?: the)? time)?(?:\s+(?:free|around|available|home|in|about|here|there|up|awake|able|back|on rota|on duty|in the office))?(?:\s+first)?`
// Said as a fact, which can also be a rant ("someone needs to tell him"):
const SOMEONE_MUST = String.raw`\b(some(?:one|body)|sum1|some1)\s+(needs? to|has to|must|should(?: probably)?|ought to|could)\b`
const WE_MUST = String.raw`\bwe\s+(need to|should(?: probably)?|have to|must|${AP}ve got to|gotta)\b`
const NEEDS_DOING = String.raw`\b(?:needs|wants)\s+(?!(?:some|any|no|every)thing\b)[a-z]{3,}ing\b`
// Words that start a time or a request after "whoever ...": "whoever's around tomorrow, could you".
const AFTER_WHOEVER = String.raw`today|tonight|tomorrow|tmrw|this|next|on|at|in the|after|before|from|by|pls|please|plz|can|could|would|will|kindly`
// A message that opens by greeting one person ("Hi Raj,", "Dad,"). A name
// typed there is the one doing it, talked about rather than spoken to.
const TO_ONE =
  /^\s*(?:(?:[Hh]i|[Hh]ey|[Hh]iya|[Hh]ello|[Dd]ear|[Mm]orning)\s+)?(?!(?:Hi|Hey|Hiya|Hello|Dear|Morning|All|Everyone|Guys|Team|Folks|Both|Ugh|Ok|Okay|So|Well|Yes|Yeah|Yep|No|Nope|Sorry|Thanks|Oh|Hmm|Wow|Btw|Also|Anyway|Right|Great|Cool|Sure|Please|Honestly|Update|Reminder|Quick)\b)[A-Z][a-z'’-]+\s*[,!]/

// A verb that says something should happen without saying what.
const VAGUE = new RegExp(
  [
    String.raw`\b(?:tak(?:e|ing)|hav(?:e|ing)|giv(?:e|ing) (?:it|this|that)) a (?:quick |proper |closer |good )?(?:look|read|squiz|peek|glance|pass|once-over)(?: (?:at|over|through))?`,
    String.raw`\blook (?:into|over|at)\b`,
    String.raw`\b(?:tighten|touch|smarten|polish)(?:ing)? (?:(?:it|this|that) )?up\b`,
    String.raw`\bsort(?:ing)? (?:(?:it|this|that|things) )?out\b`,
    String.raw`\bsort (?:it|this|that)\b`,
    String.raw`\b(?:get|have|need) (?:it|this|that|them) sorted\b`,
    String.raw`\btouch base\b`,
    String.raw`\bdo the needful\b`,
  ].join('|'),
  'gi',
)
// "Take a look at section 3 and check the totals" already says what.
const FOLLOW_UP =
  /\b(?:and|to)\s+(?:then\s+)?(?:check|confirm|fix|correct|update|change|add|remove|delete|replace|send|forward|sign|approve|book|compare|make sure|tell me|let me know|lmk|flag|mark|reply|answer|merge|test|print|order|pay|transfer|call|email|text|see (?:if|whether)|find out|work out)\b/i
// Who a phrase is asked of: whichever of these comes last before it. "Could you
// take a look" is the reader's job; "I'll take a look" is the sender's own.
const ASKER = new RegExp(String.raw`\b(?:${YOU}|${NOBODY}|whoever|please|pls|plz|kindly|mind|any chance|we (?:need to|should|have to|must)|${SOFT} to)\b`, 'gi')
const SELF = new RegExp(String.raw`\b(?:i|i${AP}(?:ll|m|d|ve)|ill|im|let me|lemme|me to)\b`, 'gi')

// When a deadline would be a needless question: the draft already gives a day,
// a date or a clock time; it's happening right now; the ask only applies if
// something comes up; it's small talk; or it's an invitation to lunch.
const DAY = String.raw`(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(?:day)?|wednesday|saturday`
const MONTH = String.raw`jan(?:uary)?|feb(?:ruary)?|march|apr(?:il)?|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?`
const TIME_WORD = String.raw`\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)\b|\d{1,2}:\d{2}\b|(?:${DAY})\b|\d{1,2}(?:st|nd|rd|th)\b|\d{1,2}\s+(?:${MONTH})\b|(?:${MONTH})\s+\d{1,2}\b|(?:today|tomorrow|tmrw)\s+(?:morning|afternoon|arvo|evening|night)\b|this (?:morning|afternoon|arvo|evening)\b|tonight\b|noon\b|midday\b`
const SET_TIME = new RegExp(String.raw`\b(?:${TIME_WORD})|\b(?:at|from|by|before|until|till|after)\s+(?:about\s+|around\s+)?\d{1,2}\b`, 'i')
// In the asking sentence itself a time only counts when it says when something
// happens ("starts at 9:00", "on Saturday"), not what the task is about
// ("flights for the 14th", "taxis booked before 1 October").
const TIMED = new RegExp(String.raw`\b(?:at|on|from|starts?|this|next)\s+(?:the\s+)?(?:about\s+|around\s+)?(?:${TIME_WORD}|\d{1,2}\b)`, 'i')
const RIGHT_NOW =
  /\b(?:right now|rn|asap|running (?:a bit |a little |so |really )?(?:late|behind)|on (?:my|the) way|omw|there in (?:a bit|a sec|\d+)|in \d+ ?(?:min|mins|minutes)|in (?:a few|five|ten) minutes)\b/i
// "Let me know if you can make it" wants an answer, even beside "and if you have any dietary requirements".
const RSVP = /\b(?:let (?:me|us) know|lmk|tell me)\s+(?:if|whether)\s+(?:you|u)(?:['’]re| are)?\s+(?:can|could|coming|free|around|able|in|keen|going)\b/i
const ONLY_IF = new RegExp(
  String.raw`\bif (?:${YOU} (?:have|need|want|spot|see|notice|find|run into|hit) (?:any|anything)|(?:anything|something)\b|there${AP}?(?:s| is| are) (?:any|anything))|\b(?:for|with) anything (?:urgent|else)\b|\bin case\b`,
  'i',
)
const SMALL_TALK = /^(?:how(?:['’]s| was| were| is| are| did)|what did you|did you (?:end up|have|get to|enjoy)|hope you)\b/i
const MEAL = /\b(?:we should|let['’]?s|we could|keen to|wanna)\s+(?:\w+\s+){0,2}?(?:grab|get|have|do|go for)\b[^.!?]*?\b(?:lunch|dinner|brunch|breakfast|coffee|drinks?|a drink|a beer|a bite|a meal)\b/i
// An ask for an answer rather than a task, in the model's reading ("Say whether...")
// or in the draft's own words. Its deadline reads "Please let me know by ...".
const REPLY_ASK =
  /^(?:let (?:me|us|the sender|them|\w+) know|say|tell (?:me|us|the sender)|reply|answer|confirm|respond|rsvp|give (?:your )?(?:thoughts|feedback|an answer)|share (?:your )?thoughts|send (?:a few |some )?(?:times|dates|availability))\b/i
const REPLY_WORDS = /\b(?:let (?:me|us) know|lmk|get back to me|tell me)\b|\bthoughts\?/i

const URGENCY_ANSWERS = [
  { label: 'Urgent', sentence: 'This is urgent.' },
  { label: 'Needed, not urgent', sentence: "It isn't urgent, but I do need it done." },
  { label: 'Truly optional', sentence: 'This is optional, only if you have time.' },
] as const
const NEEDED = 1
const TRULY_OPTIONAL = 2 // the softeners are true then, so they stay

const WHO_ANSWERS = [
  { label: "The person I'm sending it to", sentence: "I'm asking you to do this." },
  // Not "If you can, ...": the next check would read that as a hedge.
  { label: 'Anyone who can', sentence: 'Please reply if you can do it.' },
] as const
const ANYONE = 1

// A rewritten sentence shorter than this isn't saying what is needed ("file").
const MIN_WORDS = 4

const plain = (text: string) => text.trim().replace(/[\s.!]+$/, '')
const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)
const words = (text: string) => text.trim().split(/\s+/).filter(Boolean).length
const lastAt = (re: RegExp, text: string) => Math.max(-1, ...[...text.matchAll(re)].map((m) => m.index ?? -1))

// ---- Sentences

interface Span {
  text: string
  start: number
}

const EMOJI = /\p{Extended_Pictographic}/u

/** The draft's sentences (a line break or an emoji ends one too), with where each starts. */
function sentences(draft: string): Span[] {
  const spans: Span[] = []
  let from = 0
  const end = (to: number) => {
    const raw = draft.slice(from, to)
    const text = raw.trim()
    if (text) spans.push({ text, start: from + raw.indexOf(text) })
    from = to
  }
  for (let i = 0; i < draft.length; i++) {
    const c = draft.charAt(i)
    const next = draft.charAt(i + 1)
    if (c === '\n') end(i)
    else if ('.!?'.includes(c) && !'.!?'.includes(next || ' ') && /\s/.test(next || ' ')) end(i + 1)
    else if (EMOJI.test(String.fromCodePoint(draft.codePointAt(i) ?? 0))) {
      // "We should grab dinner soon 😊 Let me know..." is two sentences
      let after = i + ((draft.codePointAt(i) ?? 0) > 0xffff ? 2 : 1)
      while (draft.charAt(after) === '️') after++
      if (/\s/.test(draft.charAt(after) || ' ')) end(after)
      i = after - 1
    }
  }
  end(draft.length)
  return spans
}

const LIST_MARK = /^(?:[-*•]|\d+[.)])\s+/

/** The sentence around `index`, as it stands in the draft (without a list marker). */
export function sentenceAt(draft: string, index: number): string {
  const span = sentences(draft).find((s) => index >= s.start && index < s.start + s.text.length)
  return span ? span.text.replace(LIST_MARK, '') : ''
}

// Words the model's reading of the ask shares with a sentence, so a check can
// tell the sentence that asks from a rant or an update beside it.
const FILLER = new Set(
  'the and for with from about into over out off are was were been this that these those them they their there here your you our his her him she its can could would will should please pls just have has had get got let know some any all not than then when what who how why which whether also sender someone anyone'.split(' '),
)
const stems = (text: string) =>
  (text.toLowerCase().match(/[a-z0-9]+/g) ?? [])
    .filter((w) => w.length > 2 && !FILLER.has(w))
    .map((w) => w.replace(/s$/, ''))
function overlap(text: string, ask: string): number {
  const asked = stems(ask)
  return stems(text).filter((w) =>
    asked.some((a) => a === w || (Math.min(a.length, w.length) >= 4 && (a.startsWith(w) || w.startsWith(a)))),
  ).length
}
function askSentence(draft: string, ask: string): Span | undefined {
  let best: Span | undefined
  let most = 0
  for (const s of sentences(draft)) {
    const n = overlap(s.text, ask)
    if (n > most) [best, most] = [s, n]
  }
  return best
}

/**
 * The sentence without its greeting: the part a rewrite replaces. A hedge in
 * it stays in view - left out of the box, it would stay behind in the draft
 * ("At some point could we have a call on Thursday?").
 */
function coreOf(sentence: string): string {
  return sentence.replace(LIST_MARK, '').replace(new RegExp(String.raw`^(?:${OPENER})*`, 'i'), '')
}

/** A typed sentence with its full stop or question mark. */
const finish = (typed: string) => {
  const text = typed.trim()
  if (!text || /[.!?]$/.test(text)) return text
  return text + (/^(?:could|can|would|will|do|does|did|is|are)\b/i.test(text) ? '?' : '.')
}

// A request typed to replace a core that started mid-sentence keeps it running.
const LOWER_START = /^(?:could|can|would|will|please|pls|kindly)\b/i
/** `original` in the draft replaced by the sender's own rewrite of it. */
function swap(text: string, original: string, typed: string): string {
  if (!text.includes(original)) return text
  let next = finish(typed)
  if (/^[a-z]/.test(original) && LOWER_START.test(next)) next = next.charAt(0).toLowerCase() + next.slice(1)
  return text.replace(original, () => next)
}
const rewrote = (typed: string, original: string) =>
  words(typed) >= MIN_WORDS && plain(typed).toLowerCase() !== plain(original).toLowerCase()

// ---- Edits

/** Takes "no rush" and the like out: "No rush, but could you..." -> "Could you...". */
export function dropHedges(draft: string): string {
  const h = String.raw`(?:${HEDGE_WORDS})(?:\s+(?:at all|though|tho|then|really|honestly|lol|haha))?(?:\s+(?:on|with|for) (?:this|that|it)(?: one)?)?`
  const lead = String.raw`((?:^|[.!?]\s+|\n\s*)(?:${OPENER})*)`
  return (
    draft
      // a sentence of its own: "No pressure though!"
      .replace(new RegExp(String.raw`${START}${h}\s*[.!?]+[ \t]*`, 'gi'), '$1')
      // opening the sentence that asks: "When you get a chance, could you", "hey no rush but can u",
      // "If you have time tomorrow, could you", "Hey Sam, if you have time could you"
      .replace(
        new RegExp(
          String.raw`${lead}${h}(?:\s*[,;:-]\s*(?:but\s+)?|\s+but\s+|\s+(?=(?:${AFTER_WHOEVER}|${YOU}|it|we|i)\b))(\w)`,
          'gi',
        ),
        (_m, lead: string, c: string) => lead + (BARE_START.test(lead) ? c.toUpperCase() : c),
      )
      // set off by commas: "Could you, if you get a chance, check it", "Hey Ava, when you get a chance, it'd be"
      .replace(new RegExp(String.raw`,\s*${h}\s*,`, 'gi'), (_m, at: number, whole: string) =>
        /\b(?:you|u|to|please|pls|and|but|or|then)\s*$/i.test(whole.slice(0, at)) ? '' : ',',
      )
      // set off by "tho" in a run-on text: "tell me if its too cringe no rush tho the party's not till"
      .replace(new RegExp(String.raw`\s+(?:${RUSH}|${MAYBE})(?:\s+at all)?\s+(?:tho|though)\b,?`, 'gi'), '')
      // closing the sentence: "check it when you get a chance?", "by Thursday if possible"
      .replace(new RegExp(String.raw`,?\s+${h}(?=\s*(?:[.!?,]|[^\w\s]*\s*$))`, 'gim'), (m, at: number, whole: string) =>
        ASKS_WHETHER.test(whole.slice(0, at)) ? m : '',
      )
      .replace(/[ \t]+$/gm, '')
  )
}

/** "Would be great to have it" -> "I need it"; "it'd be great if you could send" -> "please send". */
export function firmUp(draft: string): string {
  return (
    draft
      .replace(new RegExp(String.raw`${START}${SOFT} to have (it|this|them|that)\b`, 'gi'),
        (_m, lead: string, what: string) => `${lead}I need ${what}`)
      .replace(new RegExp(String.raw`\b${SOFT} to have (it|this|them|that)\b`, 'gi'), (_m, what: string) => `I need ${what}`)
      .replace(new RegExp(String.raw`${START}${SOFT} if ${YOU} could\s+`, 'gi'), (_m, lead: string) => `${lead}Please `)
      .replace(new RegExp(String.raw`\b${SOFT} if ${YOU} could\s+`, 'gi'), 'please ')
      // "Would be great if someone could bring the bibs" -> "Please could someone bring the bibs"
      .replace(new RegExp(String.raw`${START}${SOFT} if (${NOBODY}|[\w'’-]+) could\s+`, 'gi'),
        (_m, lead: string, who: string) => `${lead}Please could ${who} `)
      .replace(new RegExp(String.raw`\b${SOFT} if (${NOBODY}|[\w'’-]+) could\s+`, 'gi'), (_m, who: string) => `please could ${who} `)
      // "Would be nice before Saturday" -> "I need it done before Saturday"
      .replace(new RegExp(String.raw`${START}${SOFT} (before|by)\b`, 'gi'),
        (_m, lead: string, by: string) => `${lead}I need it done ${by}`)
      // "If you can send your share, that'd be great" -> "Please send your share"
      .replace(new RegExp(String.raw`${START}if ${YOU} (?:can|could) ([^.!?\n]+?),?\s+${SOFT}(?=\s*(?:[,.!?]|[^\w\s]*\s*$))`, 'gim'),
        (_m, lead: string, rest: string) => `${lead}Please ${rest}`)
      .replace(/\bshould probably\b/gi, 'should')
  )
}

// "someone has to" -> "you have to"; "anyone is free" -> "you are free"; "we need to" -> "Sam needs to"
const YOU_DO = (verb: string) =>
  verb.replace(/^(?:needs|has|is|gets|wants)\b/i, (v) => ({ needs: 'need', has: 'have', is: 'are', gets: 'get', wants: 'want' })[v.toLowerCase()] ?? v)
const THEY_DO = (verb: string) =>
  verb.replace(/^(?:need|have|[’']ve got|gotta)\b/i, (v) => ({ need: 'needs', have: 'has', gotta: 'has' })[v.toLowerCase()] ?? 'has got')

// The sender says they'll do it themselves.
const ME = /^(?:me|i|myself)$/i

/**
 * Gives the task to `who` ("you", a name, or "me"). In a group the named
 * person is spoken to ("Sam, can you..."); in a message to one person they are
 * talked about ("can Sam on your team..."), because the reader isn't Sam.
 */
export function assignTo(draft: string, who: string): string {
  const you = who === 'you'
  const me = ME.test(who)
  const direct = you || me || !TO_ONE.test(draft)
  const opens = (whole: string, at: number) => OPENS.test(whole.slice(0, at))
  return (
    draft
      // "Can someone update it?" -> "Can you update it?" / "Sam, can you update it?"
      // ("Can someone on your team" -> "Can you or someone on your team": the reader answers for it)
      .replace(new RegExp(MODAL, 'gi'), (m: string, modal: string, _n: string, team: string, at: number, whole: string) => {
        if (me) return m
        if (you) return team ? `${modal} you or someone${team}` : `${modal} you`
        if (direct && opens(whole, at)) return `${who}, ${modal.toLowerCase()} you`
        return `${modal} ${who}${team}`
      })
      // "If anyone can send me their share" -> "If you can send me your share"
      // ("Let me know if anyone can help" asks whether, and stays)
      .replace(new RegExp(String.raw`${IF_ANYONE}([^.!?\n]*)`, 'gi'),
        (m: string, _n: string, verb: string, rest: string, at: number, whole: string) => {
          if (me || ASKS_WHETHER.test(whole.slice(0, at))) return m
          return you
            ? `${m.slice(0, 2)} you ${YOU_DO(verb)}${rest.replace(/\btheir\b/gi, 'your')}`
            : `${m.slice(0, 2)} ${who} ${verb}${rest}`
        })
      // "Anyone free to fill in?" -> "Are you free to fill in?" / "Sam, are you free to fill in?"
      .replace(new RegExp(ANYONE_FREE, 'gi'), (m: string, state: string, at: number, whole: string) => {
        const first = opens(whole, at)
        if (me) return m
        if (you) return `${first ? 'Are' : 'are'} you ${state} to`
        if (direct && first) return `${who}, are you ${state} to`
        return `${first ? 'Is' : 'is'} ${who} ${state} to`
      })
      // Once someone is named, "Any volunteers?" has its answer.
      .replace(new RegExp(String.raw`${START}${ANY_VOLUNTEERS}\?*[ \t]*`, 'gi'), '$1')
      // "Whoever's around tomorrow, could you..." -> "Tomorrow, could you..." / "Sam, tomorrow, could you..."
      .replace(
        new RegExp(String.raw`${START}((?:${OPENER})*)${WHOEVER}(?:\s*,\s*|\s+(?=(?:${AFTER_WHOEVER})\b))(\w)`, 'gi'),
        (m: string, lead: string, opener: string, c: string) => {
          if (you) return `${lead}${opener}${opener ? c : c.toUpperCase()}`
          return direct && !me ? `${lead}${opener}${who}, ${c}` : m
        },
      )
      // "Someone needs to call the plumber." -> "Please call the plumber." / "Sam, please call the plumber." / "I'll call the plumber."
      .replace(new RegExp(String.raw`${START}((?:${OPENER})*)(?:${SOMEONE_MUST}|${WE_MUST})\s+`, 'gi'),
        (m: string, lead: string, opener: string) => {
          if (!direct) return m
          if (me) return `${lead}${opener}I'll `
          return `${lead}${opener}${you ? (opener ? 'please ' : 'Please ') : `${who}, please `}`
        })
      // Anywhere else: "and someone has to sign for it" -> "and you have to sign" / "and Sam has to sign"
      .replace(new RegExp(SOMEONE_MUST, 'gi'), (_m, _s: string, verb: string) =>
        you || me ? `${me ? 'I' : 'you'} ${YOU_DO(verb)}` : `${who} ${verb}`)
      .replace(new RegExp(WE_MUST, 'gi'), (_m, verb: string) =>
        you || me ? `${me ? 'I' : 'you'} ${verb}` : `${who} ${THEY_DO(verb)}`)
      .replace(/[ \t]+$/gm, '')
  )
}

// ---- What is missing

interface Spot {
  at: number
  text: string
}

/** Where the draft gives a loose time for the ask: the model's own loose deadline, or loose words in the asking sentences. */
function looseTime(text: string, meaning: Meaning): Spot | undefined {
  // For an answer, only the sentence asking for it: "We should grab dinner soon"
  // is about the dinner, and a loose time for a call ("sometime this week or
  // early next") isn't the time to reply by.
  const reply = REPLY_ASK.test(meaning.ask.trim())
  const deadline = meaning.deadline.trim()
  if (!reply && deadline && LOOSE_DEADLINE.test(deadline)) {
    const at = text.toLowerCase().indexOf(deadline.toLowerCase())
    if (at >= 0) return { at, text: text.slice(at, at + deadline.length) }
  }
  const best = askSentence(text, meaning.ask)
  const asks = (s: Span) =>
    REPLY_WORDS.test(s.text) ||
    (reply ? s.start === best?.start && /\b(?:you|u|please|pls)\b/i.test(s.text) : overlap(s.text, meaning.ask) > 0)
  for (const s of sentences(text)) {
    const m = asks(s) ? LOOSE_TIME.exec(s.text) : null
    if (m) return { at: s.start + m.index, text: m[0] }
  }
}

function putAt(text: string, spot: Spot, phrase: string): string {
  const first = /[A-Z]/.test(spot.text.charAt(0)) && OPENS.test(text.slice(0, spot.at))
  return text.slice(0, spot.at) + (first ? capital(phrase) : phrase) + text.slice(spot.at + spot.text.length)
}

function cutAt(text: string, spot: Spot): string {
  const before = text.slice(0, spot.at)
  const after = text.slice(spot.at + spot.text.length)
  if (OPENS.test(before)) {
    // "When you get a chance, could you" -> "Could you"
    const rest = after.replace(/^\s*[,;:-]?\s*/, '')
    return before + (/[A-Z]/.test(spot.text.charAt(0)) ? capital(rest) : rest)
  }
  const kept = before.replace(/[,\s]+$/, '')
  if (!after.trim()) return kept
  return /^\s*[.!?,;:]/.test(after) ? kept + after.replace(/^\s+/, '') : `${kept} ${after.replace(/^\s+/, '')}`
}

/** The first hedge of `kind` in the draft that is a hedge there. */
function hedgeIn(draft: string, kind: string): string | undefined {
  for (const m of draft.matchAll(new RegExp(String.raw`\b(?:${kind})\b`, 'gi'))) {
    if (!ASKS_WHETHER.test(draft.slice(0, m.index))) return m[0]
  }
}

/** A task handed to no one in particular, and the sentence it's in. */
function unassigned(draft: string, ask: string): { phrase: string; sentence: string } | undefined {
  const spans = sentences(draft)
  const asksYou = (s: Span) => /\b(?:can|could|would|will) (?:you|u)\b|\b(?:please|pls|plz)\b/i.test(s.text)
  for (const s of spans) {
    // "Let me know if anyone has time" asks whether, not who
    const asked = [...s.text.matchAll(new RegExp(`${MODAL}|${IF_ANYONE}|${ANYONE_FREE}|${ANY_VOLUNTEERS}`, 'gi'))]
      .find((m) => !ASKS_WHETHER.test(s.text.slice(0, m.index)))
    const open =
      asked ??
      // "Thanks to whoever restocked it" thanks someone; "whoever's free, could you" asks
      (/\b(?:you|u|please|pls|plz|can|could|would|will|kindly)\b/i.test(s.text) ? new RegExp(String.raw`\b${WHOEVER}`, 'i').exec(s.text) : null)
    if (open) return { phrase: open[0], sentence: s.text }
    // "Someone needs to renew it. Could you take care of it?" already says who,
    // and "we should grab dinner" is an invitation.
    const stated = new RegExp(`${SOMEONE_MUST}|${WE_MUST}|${NEEDS_DOING}`, 'i').exec(s.text)
    if (stated && overlap(s.text, ask) && !MEAL.test(s.text) && !spans.some((o) => o !== s && asksYou(o)))
      return { phrase: stated[0], sentence: s.text }
  }
}

/** A vague verb the reader is asked to act on, and the part of its sentence to rewrite. */
function vagueAsk(draft: string): { phrase: string; core: string } | undefined {
  for (const s of sentences(draft)) {
    for (const m of s.text.matchAll(VAGUE)) {
      const at = m.index ?? 0
      const before = s.text.slice(0, at)
      const asker = lastAt(ASKER, before)
      const self = lastAt(SELF, before)
      const asked = asker !== self ? asker > self : new RegExp(String.raw`^(?:${OPENER})*$`, 'i').test(before)
      if (asked && !FOLLOW_UP.test(s.text.slice(at + m[0].length))) return { phrase: m[0], core: coreOf(s.text) }
    }
  }
}

const deadlineLine = (phrase: string, reply: boolean) =>
  reply ? `Please let me know ${phrase}.` : `I need this ${phrase}.`
const NO_DEADLINE = "There's no deadline for this."

// The model's note when it found nothing asked ("No ask was stated. Add what
// you want done, such as washing the dishes."): seen on hints and venting in
// the 100-draft test, never on a plain update or a thank-you.
const NO_ASK_NOTE = /\bno (?:ask|request)\b/i

/** For a draft that only hints: the sender says what they want, if anything. */
const hinted = (): MissingItem => ({
  key: 'what',
  title: "It doesn't ask for anything directly",
  question:
    'If you want them to do something, say what (and who and by when, if it matters). If you only meant to let them know, leave this.',
  quick: [],
  placeholder: '',
  prefill: '',
  hint: "Such as “Could someone take the bins out tonight?” Press Enter when it's done.",
  sentence: finish,
  answered: (answer) => words(answer.typed) >= MIN_WORDS,
})

/** What the draft leaves out, given the rewrite model's reading of it and its notes. */
export function findMissing(draft: string, meaning: Meaning, notes: readonly string[] = []): MissingItem[] {
  // An update or a thank-you asks nothing, so it owes the reader none of this.
  // A hint ("the bins are overflowing again") may: only the sender knows.
  if (!meaning.ask.trim()) return notes.some((note) => NO_ASK_NOTE.test(note)) ? [hinted()] : []
  const items: MissingItem[] = []
  const reply = REPLY_ASK.test(meaning.ask.trim())
  const asking =
    (reply ? sentences(draft).find((s) => REPLY_WORDS.test(s.text)) : undefined) ?? askSentence(draft, meaning.ask)
  const deadline = meaning.deadline.trim()
  const firm = !!deadline && !LOOSE_DEADLINE.test(deadline)
  // "We should grab lunch at some point - no pressure" is an invitation, not a task.
  const invite = !!asking && MEAL.test(asking.text)
  const loose = looseTime(draft, meaning)
  // "Let me know what works when you can": the reply has no time, whatever the
  // model took as the deadline (the day of the meeting being moved).
  const inReply =
    !!loose && sentences(draft).some((s) => REPLY_WORDS.test(s.text) && loose.at >= s.start && loose.at < s.start + s.text.length)

  if ((!firm || inReply) && !invite) {
    const bare = asking ? asking.text.replace(new RegExp(String.raw`^(?:${OPENER})*`, 'i'), '') : ''
    const elsewhere = asking ? draft.slice(0, asking.start) + '\n' + draft.slice(asking.start + asking.text.length) : draft
    const needless =
      SET_TIME.test(elsewhere) ||
      RIGHT_NOW.test(draft) ||
      (!!asking &&
        (TIMED.test(asking.text) || (ONLY_IF.test(asking.text) && !RSVP.test(asking.text)) || SMALL_TALK.test(bare)))
    const answer = reply || inReply
    if (loose || !needless) {
      items.push({
        key: 'when',
        question: `${loose ? `“${loose.text}” doesn't give a time. ` : ''}When do you need ${answer ? 'an answer' : 'it'}?`,
        quick: QUICK_DEADLINES.map((d) => ({ label: d.label, sentence: d.phrase ? deadlineLine(d.phrase, answer) : NO_DEADLINE })),
        placeholder: '3pm Friday',
        sentence: (typed) => (deadlinePhrase(typed) ? deadlineLine(deadlinePhrase(typed), answer) : ''),
        // The time goes where the loose words were: "send it when you get a chance" -> "send it by Friday".
        settle: (text, answer) => {
          const phrase = answer.quick !== null ? (QUICK_DEADLINES[answer.quick]?.phrase ?? '') : deadlinePhrase(answer.typed)
          const spot = looseTime(text, meaning)
          if (!spot) return { draft: text, done: false }
          return phrase ? { draft: putAt(text, spot, phrase), done: true } : { draft: cutAt(text, spot), done: false }
        },
      })
    }
  }

  const nobody = FINE_IF_NOT.test(draft) ? undefined : unassigned(draft, meaning.ask)
  if (nobody) {
    const quoted = `“${nobody.phrase.toLowerCase()}” doesn't say who.`
    const whoOf = (answer: Answer) => (answer.quick !== null ? 'you' : plain(answer.typed))
    if (assignTo(draft, 'Sam') !== draft) {
      items.push({
        key: 'who',
        question: `${quoted} Who should do it?`,
        quick: WHO_ANSWERS,
        placeholder: 'A name, such as Sam',
        sentence: (typed) =>
          !plain(typed) ? '' : ME.test(plain(typed)) ? "I'll do it myself." : `I'm asking ${plain(typed)} to do this.`,
        settle: (text, answer) => {
          // Left open on purpose: the reader is told how to take it.
          if (answer.quick === ANYONE) return { draft: text, done: false }
          const changed = assignTo(text, whoOf(answer))
          return { draft: changed, done: changed !== text }
        },
      })
    } else {
      // Nothing to swap a name into ("the battery needs changing"), so the
      // sender says it in their own words rather than getting a sentence that
      // contradicts theirs.
      items.push({
        key: 'who',
        question: `${quoted} Rewrite this sentence to name who should do it, or let anyone who can take it:`,
        quick: [WHO_ANSWERS[ANYONE]],
        placeholder: '',
        prefill: nobody.sentence,
        hint: "Name them, such as “Ravi, can you change the smoke alarm battery tonight?” Press Enter when it's done.",
        sentence: () => '',
        answered: (answer) => answer.quick !== null || rewrote(answer.typed, nobody.sentence),
        settle: (text, answer) =>
          answer.quick !== null ? { draft: text, done: false } : { draft: swap(text, nobody.sentence, answer.typed), done: true },
      })
    }
  }

  const vague = vagueAsk(draft)
  if (vague) {
    items.push({
      key: 'what',
      question: `“${vague.phrase.toLowerCase()}” could mean a lot of things. Rewrite this to say exactly what you need:`,
      quick: [],
      placeholder: '',
      prefill: vague.core,
      hint: "Say what should be done and to what, such as “Could you fix the totals in the numbers section so they match the finance report?” Press Enter when it's done.",
      sentence: () => '',
      answered: (answer) => rewrote(answer.typed, vague.core),
      settle: (text, answer) => ({ draft: swap(text, vague.core, answer.typed), done: true }),
    })
  }

  // "No rush, but by Friday" is true and says nothing new ("no rush ... for
  // tonight" doesn't say by when); "no worries if not" and "would be great"
  // leave it open whether it's needed at all.
  const dated = firm && /\b(?:by|before|until|till|no later than|due)\b/i.test(draft)
  const hedge = invite || FINE_IF_NOT.test(draft) ? undefined : (SOFTENER.exec(draft)?.[0] ?? hedgeIn(draft, MAYBE) ?? (dated ? undefined : hedgeIn(draft, RUSH)))
  if (hedge) {
    // A deadline already says "needed, not urgent"; "no worries if not" already says "optional".
    const says = (i: number) => (i === NEEDED && firm) || (i === TRULY_OPTIONAL && /\bno worries if\b/i.test(hedge))
    items.push({
      key: 'urgency',
      question: `You wrote “${hedge.toLowerCase()}”. How urgent is it, really?`,
      quick: URGENCY_ANSWERS.map((a, i) => (says(i) ? { ...a, sentence: '' } : a)),
      placeholder: '',
      sentence: () => '',
      settle: (text, answer) => ({
        draft: answer.quick === TRULY_OPTIONAL ? text : firmUp(dropHedges(text)),
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
// ("Can someone" -> "Sam, can you"), and it has to be found as the sender saw
// it. The deadline goes before the hedges are dropped, so it can take the
// place of "when you get a chance".
const SETTLE_ORDER: MissingKey[] = ['what', 'who', 'when', 'urgency']

/** The draft with the sender's answers in it, ready to rewrite. */
export function applyAnswers(
  draft: string,
  items: MissingItem[],
  answers: Partial<Record<MissingKey, Answer>>,
): string {
  let text = draft
  const added: { key: MissingKey; sentence: string }[] = []
  const ordered = [...items].sort((a, b) => SETTLE_ORDER.indexOf(a.key) - SETTLE_ORDER.indexOf(b.key))
  // A deadline from the sender says how soon too, so "isn't urgent, but needed" would only repeat it.
  const when = answers.when
  const dated = !!when && (when.quick !== null ? !!QUICK_DEADLINES[when.quick]?.phrase : !!deadlinePhrase(when.typed))
  for (const item of ordered) {
    const answer = answers[item.key]
    if (!answer || !isAnswered(item, answer)) continue
    const settled = item.settle?.(text, answer) ?? { draft: text, done: false }
    text = settled.draft
    if (settled.done || (item.key === 'urgency' && answer.quick === NEEDED && dated)) continue
    const sentence = answer.quick !== null ? (item.quick[answer.quick]?.sentence ?? '') : item.sentence(answer.typed)
    if (sentence) added.push({ key: item.key, sentence })
  }
  // Added in the order the questions were asked, not the order they were settled in.
  const asked = items.map((item) => item.key)
  added.sort((a, b) => asked.indexOf(a.key) - asked.indexOf(b.key))
  return added.length ? addToDraft(text, added.map((a) => a.sentence).join(' ')) : text
}
