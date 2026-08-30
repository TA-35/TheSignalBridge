import type { DecodeResult } from '@/types/decode'
import { localDecode } from './localDecoder'

const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined

// Calls POST /api/decode. 
// Falls back to the localDecode for now (backend 'ai_decoder.py' not implemented yet)
// app/services/ai_decoder.py currently raises NotImplementedError.

export async function decodeMessage(message: string): Promise<DecodeResult> {
  if (API_BASE) {
    try {
      const response = await fetch(`${API_BASE}/api/decode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      if (response.ok) {
        return (await response.json()) as DecodeResult
      }
    } catch {
      // Network error, fall through to the local extractor.
    }
  }

  return localDecode(message)
}
