import type { Pattern } from '@/types/pattern'
import { LOCAL_PATTERNS } from './localPatterns'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined

// Calls GET /api/patterns. 
// Falls back to the local seed list when the backend isn't reachable
export async function getPatterns(): Promise<Pattern[]> {
  if (API_BASE) {
    try {
      const response = await fetch(`${API_BASE}/api/patterns`)
      if (response.ok) {
        const patterns = (await response.json()) as Pattern[]
        if (patterns.length) return patterns
      }
    } catch {
      // Network error, fall through to the local seed.
    }
  }

  return LOCAL_PATTERNS
}
