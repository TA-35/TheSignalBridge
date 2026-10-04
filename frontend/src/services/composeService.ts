import type { ComposeQuick, ComposeResult } from '@/types/compose'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined

// Kept in sync with MAX_MESSAGE_LENGTH in the decode and review services,
// and with the backend's own limit.
export const MAX_MESSAGE_LENGTH = 5000

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
