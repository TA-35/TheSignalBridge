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
