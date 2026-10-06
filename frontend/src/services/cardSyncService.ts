// Library cards that follow an account between devices.
//
// Only cards saved from the pattern library sync, and only as a pointer:
// which curated row, when it was kept, when it was last opened. A card made
// from a decode carries an excerpt of the reader's own message, so it stays
// in the browser that made it - see docs/api-contract.md, "Data retention".
//
// Every call here is best-effort. localStorage is the source of truth for
// what the Study page shows; this is a copy that lets a second device start
// from the same place. A failed sync must never cost someone a saved card,
// so nothing in this file throws.

const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined

export interface RemoteCard {
  pattern_id: string
  saved_at: string | null
  last_opened_at: string | null
}

function url(path = ''): string | null {
  if (!API_BASE) return null
  return `${API_BASE}/api/cards${path}`
}

/** Everything this account has kept. Empty on any failure. */
export async function fetchCards(): Promise<RemoteCard[]> {
  const endpoint = url()
  if (!endpoint) return []
  try {
    const response = await fetch(endpoint, { credentials: 'include' })
    if (!response.ok) return []
    return (await response.json()) as RemoteCard[]
  } catch {
    return []
  }
}

/** Keep a card, or update when it was last opened. Idempotent server-side. */
export async function pushCard(
  patternId: string,
  times: { saved_at?: string | null; last_opened_at?: string | null },
): Promise<void> {
  const endpoint = url(`/${encodeURIComponent(patternId)}`)
  if (!endpoint) return
  try {
    await fetch(endpoint, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(times),
    })
  } catch {
    // Local save already happened; the next sign-in replays it.
  }
}

export async function removeCard(patternId: string): Promise<void> {
  const endpoint = url(`/${encodeURIComponent(patternId)}`)
  if (!endpoint) return
  try {
    await fetch(endpoint, { method: 'DELETE', credentials: 'include' })
  } catch {
    // Same: the card is gone locally, which is what the reader asked for.
  }
}
