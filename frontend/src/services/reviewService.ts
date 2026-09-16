import type { FullReview, QuickReview } from '@/types/review'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined

// Kept in sync with MAX_MESSAGE_LENGTH in backend/app/routes/review.py and
// routes/decode.py.
export const MAX_MESSAGE_LENGTH = 5000

/**
 * Two-stage review.
 *
 * Stage one returns in milliseconds and is what the user sees immediately -
 * spans to highlight, fields found, what is missing. Stage two takes seconds
 * and replaces it with the model's reading.
 *
 * The staging exists because the model call measures 5-9 seconds. A single
 * request would mean a spinner on every message; this way the page is useful
 * straight away and improves, and if stage two fails the user still has
 * stage one rather than an error.
 *
 * `onQuick` fires as soon as stage one lands. The promise resolves with the
 * full reading. Neither stage throws: a failure resolves to a degraded
 * result, because a reader who pasted a message should get something.
 */
export async function reviewMessage(
  message: string,
  onQuick?: (quick: QuickReview) => void,
): Promise<FullReview> {
  if (!API_BASE) return offlineReview('no API configured')

  // Stage one, awaited only long enough to paint something.
  if (onQuick) {
    try {
      const response = await fetch(`${API_BASE}/api/review/quick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      if (response.ok) onQuick((await response.json()) as QuickReview)
    } catch {
      // Stage one is an optimisation. Losing it costs the instant paint,
      // not the answer, so fall through to stage two regardless.
    }
  }

  try {
    const response = await fetch(`${API_BASE}/api/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    if (!response.ok) return offlineReview(`API returned ${response.status}`)
    return (await response.json()) as FullReview
  } catch {
    return offlineReview('network error')
  }
}

/** What the caller gets when the API cannot be reached at all. Same shape as
 *  a server-side degrade, so the UI has one thing to render. */
function offlineReview(reason: string): FullReview {
  return {
    stage: 'review',
    degraded: true,
    degraded_reason: [reason],
    summary: '',
    claims: [],
    missing: [],
  }
}
