// Purely descriptive ("opened 3 weeks ago") — never a count, streak, or score (AC 2.3.1).
export function describeLastOpened(iso: string | null): string {
  if (!iso) return 'not opened yet'

  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'opened today'
  if (days === 1) return 'opened 1 day ago'
  if (days < 14) return `opened ${days} days ago`

  const weeks = Math.floor(days / 7)
  if (weeks < 8) return `opened ${weeks} weeks ago`

  const months = Math.floor(days / 30)
  return `opened ${months} month${months === 1 ? '' : 's'} ago`
}

// The Study card footer, which reads as a status line rather than a sentence:
// "Opened yesterday", "Opened 2 days ago", "Opened 18 Sep". Still no
// count or score - it says when, never how often or how well.
export function describeOpened(iso: string | null): string {
  if (!iso) return 'Not opened yet'

  const then = new Date(iso)
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000)
  if (days <= 0) return 'Opened today'
  if (days === 1) return 'Opened yesterday'
  if (days < 7) return `Opened ${days} days ago`

  // Past a week the day of the month is easier to place than a count of them.
  return `Opened ${then.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
}

// Groups the list under "when you saved it" headings. Buckets, not exact
// dates: the reader is scanning for roughly when, and a heading per day would
// be one heading per card.
export function savedBucket(iso: string): 'today' | 'yesterday' | 'week' | 'earlier' {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 7) return 'week'
  return 'earlier'
}
