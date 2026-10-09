// Joins the pattern library, the user's saved cards (stores/cards.ts) and the
// local activity log into the CardProgress lists the dashboard works from.
import { computed, onMounted, ref } from 'vue'
import { useActivityStore } from '@/stores/activity'
import { useCardsStore } from '@/stores/cards'
import { getPatterns } from '@/services/patternsService'
import type { Pattern, SavedCard } from '@/types/pattern'
import { dateKey, type CardProgress } from '@/utils/progress'

// Library names can arrive with their own quote marks (see StudyView), the
// dashboard adds its own, so strip them first
function phrase(name: string): string {
  return name.replace(/^["'‘’“”]+|["'‘’“”]+$/g, '').trim() || name
}

const day = (iso: string | null) => (iso ? dateKey(new Date(iso)) : undefined)

// Reviews are keyed by pattern id for library cards and by card id for cards
// saved from a decode, so the same phrase keeps its history if it's re-saved
export function reviewKey(card: Pick<SavedCard, 'id' | 'patternId'>): string {
  return card.patternId ?? card.id
}

export function buildCardProgress(
  patterns: Pattern[],
  saved: SavedCard[],
  viewed: string[],
  reviews: Record<string, string[]>,
): { library: CardProgress[]; all: CardProgress[] } {
  const seen = new Set(viewed)
  const savedByPattern = new Map(saved.filter((c) => c.patternId).map((c) => [c.patternId as string, c]))

  const fromCard = (c: SavedCard) => ({
    saved: true,
    viewed: true, // saving a card means they opened it
    // older cards opened before tracking started still count once
    reviews: reviews[reviewKey(c)] ?? (c.lastOpened ? [day(c.lastOpened) as string] : []),
    firstSeen: day(c.savedAt),
    cardId: c.id,
  })

  const library: CardProgress[] = patterns.map((p) => {
    const card = savedByPattern.get(p.id)
    return {
      id: p.id,
      text: phrase(p.name),
      category: p.category,
      ...(card ? fromCard(card) : { saved: false, viewed: seen.has(p.id), reviews: [] }),
    }
  })

  // cards saved from a decoded message that don't match a library pattern
  // still deserve a refresher, they just don't count towards library progress
  const libraryIds = new Set(patterns.map((p) => p.id))
  const messageOnly: CardProgress[] = saved
    .filter((c) => !c.patternId || !libraryIds.has(c.patternId))
    .map((c) => ({ id: c.id, text: phrase(c.name), category: c.category ?? 'From your messages', ...fromCard(c) }))

  return { library, all: [...library, ...messageOnly] }
}

export function useProgressSources() {
  const activity = useActivityStore()
  const cardsStore = useCardsStore()
  const patterns = ref<Pattern[]>([])
  const loading = ref(true)

  onMounted(async () => {
    try {
      patterns.value = await getPatterns()
    } finally {
      loading.value = false
    }
  })

  const built = computed(() => buildCardProgress(patterns.value, cardsStore.cards, activity.viewed, activity.reviews))
  return {
    activity,
    loading,
    libraryCards: computed(() => built.value.library),
    allCards: computed(() => built.value.all),
  }
}
