// Progress-dashboard data that follows an account between devices.
//
// Same rules as cardSyncService.ts: only dates, feature names, minute counts
// and library pattern ids travel. The focus timer's free-text intent never
// leaves the browser. localStorage stays the source of truth, every call is
// best-effort, and nothing in this file throws - a failed sync must never
// cost someone their days or their badges.

const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined

export type SyncFeature = 'opened' | 'decoder' | 'compose' | 'study' | 'library'

export interface RemoteActivity {
  device_id: string
  date: string
  feature: SyncFeature
  minutes: number
}

export interface RemotePhraseEvent {
  pattern_id: string
  kind: 'viewed' | 'reviewed'
  date: string
}

export interface ProgressSnapshot {
  activity: RemoteActivity[]
  phrase_events: RemotePhraseEvent[]
}

export interface ProgressUpload {
  device_id: string
  activity: Omit<RemoteActivity, 'device_id'>[]
  phrase_events: RemotePhraseEvent[]
}

function url(): string | null {
  return API_BASE ? `${API_BASE}/api/progress` : null
}

/**
 * Send everything this device has and get the account's whole set back.
 * The server merges (it's an idempotent upsert), so replaying is safe.
 * Null on any failure - the caller just keeps what it has.
 */
export async function pushProgress(upload: ProgressUpload): Promise<ProgressSnapshot | null> {
  const endpoint = url()
  if (!endpoint) return null
  try {
    const response = await fetch(endpoint, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(upload),
    })
    if (!response.ok) return null
    return (await response.json()) as ProgressSnapshot
  } catch {
    return null
  }
}

/** Settings' "delete" while signed in, so cleared progress doesn't sync back. */
export async function clearProgress(): Promise<void> {
  const endpoint = url()
  if (!endpoint) return
  try {
    await fetch(endpoint, { method: 'DELETE', credentials: 'include' })
  } catch {
    // Cleared locally already, which is what the reader asked for.
  }
}
