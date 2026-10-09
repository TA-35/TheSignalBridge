// Joins the pattern library, the user's saved cards and the local activity log
// into the CardProgress list the dashboard works from.
import { computed } from 'vue'
import { useActivityStore } from '@/stores/activity'
import type { CardProgress } from '@/utils/progress'

export interface LibraryPhrase {
  id: string
  text: string
  category: string
}

export function buildCardProgress(
  phrases: LibraryPhrase[],
  savedIds: Set<string>,
  viewed: string[],
  reviews: Record<string, string[]>,
): CardProgress[] {
  const seen = new Set(viewed)
  return phrases.map((p) => ({
    ...p,
    saved: savedIds.has(p.id),
    // saving a card means they opened it too
    viewed: seen.has(p.id) || savedIds.has(p.id),
    reviews: reviews[p.id] ?? [],
  }))
}

// TODO(wire-up): read the real library phrases and saved card ids from the cards store
export function useProgressSources(getPhrases: () => LibraryPhrase[], getSavedIds: () => string[]) {
  const activity = useActivityStore()
  const cards = computed(() =>
    buildCardProgress(getPhrases(), new Set(getSavedIds()), activity.viewed, activity.reviews),
  )
  return { cards, activity }
}
