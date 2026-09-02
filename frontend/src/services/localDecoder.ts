import type { DecodeResult, ElementKey } from '@/types/decode'
import { NOT_SPECIFIED } from '@/types/decode'
import { guessCategory } from './localPatterns'

// Placeholder extraction used until the backend AI model
// is decided and POST /api/decode is implemented. 
// Same response shape as the real contract 
// An unmatched field is left `null`.

// Mirrors is_meaningless() in backend/app/services/extraction.py: fewer than
// three alphabetic word-tokens of length >= 2. Kept here so the offline path
// judges a message exactly as the server would - one rule, not two.
const MEANINGFUL_WORD = /[A-Za-z]{2,}/g

export function isMeaningless(message: string): boolean {
  return (message.trim().match(MEANINGFUL_WORD) ?? []).length < 3
}

function firstMatch(text: string, patterns: RegExp[]): string | null {
  for (const pattern of patterns) {
    const match = text.match(pattern)
    if (match) return match[0].trim()
  }
  return null
}

const PROMPTS: Record<ElementKey, string> = {
  time: 'What time do you need this by?',
  task: 'What exactly needs to be done?',
  deadline: 'When is this actually due?',
  for_whom: 'Who is this for?',
}

// simple mannual decode 
export function localDecode(message: string): DecodeResult {
  const time = firstMatch(message, [
    /\b(?:at|by)\s\d{1,2}(?::\d{2})?\s?(?:am|pm)\b/i,
    /\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday)\b/i,
  ])
  const task = firstMatch(message, [
    /(?:take a look at|review|look at|draft|prepare|fix|update|tighten up)[^.?!\n]*/i,
  ])
  const deadline = firstMatch(message, [
    /\bbefore [^.,?!\n]*/i,
    /\bby (?:eod|end of day|friday|monday|tomorrow)[^.,?!\n]*/i,
    /\bthis week\b/i,
  ])
  const forWhom = firstMatch(message, [/\bfor (?:the )?(?:leadership|client|team|board)[^.,?!\n]*/i])

  const elements: Record<ElementKey, string> = {
    time: time ?? NOT_SPECIFIED,
    task: task ?? NOT_SPECIFIED,
    deadline: deadline ?? NOT_SPECIFIED,
    for_whom: forWhom ?? NOT_SPECIFIED,
  }

  const covered = (Object.keys(elements) as ElementKey[]).filter((key) => elements[key] !== NOT_SPECIFIED)
  const missing = (Object.keys(elements) as ElementKey[])
    .filter((key) => elements[key] === NOT_SPECIFIED)
    .map((field) => ({ field, prompt: PROMPTS[field] }))

  const category = guessCategory(message)

  return { elements, covered, missing, category }
}
