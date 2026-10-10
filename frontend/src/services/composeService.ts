import type { ComposeQuick, ComposeResult } from '@/types/compose'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined

// Lower than Decode's 5000: the rewrite model was trained on messages up to
// ~1,500 characters, and much past 2,000 its reply outgrows its token budget.
// Kept in sync with backend/app/routes/compose.py and the inference service's
// compose_service.py, which both enforce it too.
export const MAX_MESSAGE_LENGTH = 2000

// The message is the sender's own draft, so a verdict on it belongs to the
// form, not to the fallback path - same split as decodeService.
export class EmptyMessageError extends Error {
  constructor(message = 'Please paste the message you want to send') {
    super(message)
    this.name = 'EmptyMessageError'
  }
}

export class MessageTooLongError extends Error {
  constructor(message = `Message is too long (limit is ${MAX_MESSAGE_LENGTH} characters).`) {
    super(message)
    this.name = 'MessageTooLongError'
  }
}

/** What the caller gets when no rewrite can be shown. Same shape as a
 *  server-side degrade, so the page has one thing to render. */
function unavailable(reason: string): ComposeResult {
  return {
    stage: 'compose',
    degraded: true,
    degraded_reason: [reason],
    rewrite: null,
    notes: [],
    meaning: { ask: '', deadline: '', urgency: '', tone: '', implied: '' },
  }
}

// --------------------------------------------------------------------------
// Development stand-in
// For checking front-end style when model gives back different result.
//
// /api/compose does not exist yet, so every real call fails and the page can
// only ever reach its "no rewrite" state - the two states that matter most
// are unreachable. This fakes the service so the UI can be built and
// reviewed before the model lands.
//
// Off unless VITE_COMPOSE_MOCK=1 is set (put it in frontend/.env.local,
// which is gitignored). Delete this block the day the endpoint is live.
// --------------------------------------------------------------------------

const MOCK = import.meta.env.VITE_COMPOSE_MOCK === '1'

// Phrases the real classifiers would flag. Enough to decide which of the two
// answers to fake, so both can be seen from the sample message.
const HEDGES = /might be good|when you get a chance|if you get a chance|no pressure|sometime|would be great/i

function mockResult(message: string): ComposeResult {
  if (!HEDGES.test(message)) {
    return {
      stage: 'compose',
      degraded: false,
      rewrite: message,
      notes: ['Already clear, kept as written.'],
      meaning: {
        ask: 'Send the Q3 sales report',
        deadline: '3pm Thursday',
        urgency: 'medium',
        tone: 'direct',
        implied: 'The ask, who does it and the deadline are all stated directly.',
      },
      signals: [{ model: 'politeness', label: 'medium', confidence: 0.58 }],
      checks: { entities_kept: true, nothing_added: true },
      model: 'mock',
    }
  }

  return {
    stage: 'compose',
    degraded: false,
    rewrite:
      "Hi Sam, please send me the Q3 numbers before Friday's meeting. This is needed, not optional. Thanks!",
    notes: [
      '"Might be good" was a polite way of asking. It\'s now a direct request.',
      '"If you get a chance" made it sound optional, so the rewrite says it\'s needed.',
      'The ask and the deadline now come first, in one sentence.',
    ],
    meaning: {
      ask: 'Send the Q3 numbers',
      deadline: "Before Friday's meeting",
      urgency: 'high',
      tone: 'friendly',
      implied: 'Required, not optional',
    },
    signals: [
      { model: 'politeness', label: 'high', confidence: 0.65 },
      { model: 'circa', label: 'indirect', confidence: 0.52 },
    ],
    checks: { entities_kept: true, nothing_added: true },
    model: 'mock',
  }
}

/**
 * Two-stage, like the decode page.
 *
 * Stage one is the three classifiers: how the draft reads, in milliseconds.
 * Stage two is the rewrite. The team expects the model to answer in a second
 * or two, which would make the staging barely visible - but that is a verbal
 * estimate for a model that is still being trained, and building it in costs
 * almost nothing now against a rewrite later.
 *
 * Neither stage throws for an outage: a draft that could not be rewritten
 * still gets its signals and an honest line about why.
 */
export async function composeMessage(
  message: string,
  onQuick?: (quick: ComposeQuick) => void,
): Promise<ComposeResult> {
  if (message.length > MAX_MESSAGE_LENGTH) throw new MessageTooLongError()
  if (!message.trim()) throw new EmptyMessageError()

  if (MOCK) {
    // Long enough to see the loading state, short enough to work in.
    await new Promise((resolve) => setTimeout(resolve, 600))
    return mockResult(message)
  }

  if (!API_BASE) return unavailable('no API configured')

  if (onQuick) {
    try {
      const response = await fetch(`${API_BASE}/api/compose/quick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      if (response.ok) onQuick((await response.json()) as ComposeQuick)
    } catch {
      // Stage one is an optimisation. Losing it costs the instant paint,
      // not the answer.
    }
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}/api/compose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
  } catch {
    return unavailable('network error')
  }

  if (response.status === 400) {
    const body = (await response.json().catch(() => ({}))) as { error?: string }
    throw new EmptyMessageError(body.error)
  }
  if (response.status === 413) {
    const body = (await response.json().catch(() => ({}))) as { error?: string }
    throw new MessageTooLongError(body.error)
  }
  if (!response.ok) return unavailable(`the rewriter answered ${response.status}`)

  const result = (await response.json()) as ComposeResult

  // Belt and braces. The grounding check runs server-side and sets
  // `degraded`, but a rewrite is text someone will paste into an email, so
  // the page refuses to show one that arrives flagged.
  if (result.degraded) return { ...result, rewrite: null }
  return result
}
