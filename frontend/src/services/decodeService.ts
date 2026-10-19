import type { DecodeResult } from '@/types/decode'
import { isMeaningless, localDecode } from './localDecoder'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined

// Contract wording, kept identical to the backend's 400 body.
const EMPTY_MESSAGE = 'Please enter a message'

// Kept in sync with MAX_MESSAGE_LENGTH in backend/app/routes/decode.py
// see docs/api-contract.md.
export const MAX_MESSAGE_LENGTH = 5000

function tooLongMessage(limit: number = MAX_MESSAGE_LENGTH): string {
  return `Message is too long (limit is ${limit} characters).`
}

// Thrown when the message itself is the problem, as opposed to the API being
// unreachable. Callers render this as the form's error state; anything else
// falls back to the offline extractor.
export class EmptyMessageError extends Error {
  constructor(message: string = EMPTY_MESSAGE) {
    super(message)
    this.name = 'EmptyMessageError'
  }
}

// Same treatment as EmptyMessageError: a verdict on the message, not an
// outage, so it must reach the user instead of silently falling back to the
// offline extractor (which would just run the same oversized text locally).
export class MessageTooLongError extends Error {
  constructor(message: string = tooLongMessage()) {
    super(message)
    this.name = 'MessageTooLongError'
  }
}

// The API's per-connection limit (backend/app/limiter.py) was reached. Shown
// rather than silently decoded offline: the reader would otherwise get a
// thinner answer with no idea why.
export class RateLimitedError extends Error {
  retryAfter: number | null
  constructor(retryAfter: number | null) {
    super('Too many requests. Please wait a moment and try again.')
    this.name = 'RateLimitedError'
    this.retryAfter = retryAfter
  }
}

/** Seconds from a Retry-After header, or null when absent or not a number. */
export function retryAfterSeconds(response: Response): number | null {
  const raw = response.headers.get('Retry-After')
  const seconds = raw === null ? NaN : Number(raw)
  return Number.isFinite(seconds) && seconds >= 0 ? Math.ceil(seconds) : null
}

// Calls POST /api/decode, falling back to localDecode when the API is
// unreachable. A 400/413 is the server's verdict on the message, not an
// outage, so it propagates instead of silently producing a local result.
export async function decodeMessage(message: string): Promise<DecodeResult> {
  // Checked client-side first so an oversized paste never leaves the
  // browser - the backend enforces the same limit independently either way.
  if (message.length > MAX_MESSAGE_LENGTH) throw new MessageTooLongError()

  if (API_BASE) {
    let response: Response | null = null
    try {
      response = await fetch(`${API_BASE}/api/decode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
    } catch {
      // Network error - leave response null and fall through to local.
      response = null
    }

    if (response) {
      if (response.status === 400) {
        const body = (await response.json().catch(() => ({}))) as { error?: string }
        throw new EmptyMessageError(body.error ?? EMPTY_MESSAGE)
      }
      if (response.status === 413) {
        const body = (await response.json().catch(() => ({}))) as { error?: string }
        throw new MessageTooLongError(body.error ?? tooLongMessage())
      }
      if (response.status === 429) throw new RateLimitedError(retryAfterSeconds(response))
      if (response.ok) {
        return (await response.json()) as DecodeResult
      }
      // 5xx or anything else: treat as an outage and use the local extractor.
    }
  }

  // Offline path applies the same rule the server would have applied, so the
  // message is judged identically whether or not the API is reachable.
  if (isMeaningless(message)) throw new EmptyMessageError()

  return localDecode(message)
}
