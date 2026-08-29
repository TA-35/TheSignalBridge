// Mirrors GET /api/patterns  
// the curated pattern-library row.
// Read-only content; never carries user data.

export interface Pattern {
  id: string
  name: string
  category: string
  implies: string
  why_misread: string
  source: string
}

// A pattern the user has explicitly chosen to keep. Lives only in
// localStorage.
export interface SavedCard extends Pattern {
  savedAt: string
  lastOpened: string | null
}
