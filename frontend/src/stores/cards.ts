import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { Pattern, SavedCard } from '@/types/pattern'

const STORAGE_KEY = 'readtheroom.cards'

function load(): SavedCard[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as SavedCard[]) : []
  } catch {
    return []
  }
}

// Saved cards never leave the browser, see docs/api-contract.md "Data
// TODO: Can I save card in database if it doesn't contain any personal info??
export const useCardsStore = defineStore('cards', () => {
  const cards = ref<SavedCard[]>(load())

  watch(
    cards,
    (value) => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    },
    { deep: true },
  )

  // F11: cards not opened in a while surface higher. Never-opened cards
  // count as the most neglected. No number is derived or displayed from this.
  const sortedByNeglect = computed(() =>
    [...cards.value].sort((a, b) => {
      const at = a.lastOpened ? new Date(a.lastOpened).getTime() : -Infinity
      const bt = b.lastOpened ? new Date(b.lastOpened).getTime() : -Infinity
      return at - bt
    }),
  )

  function isSaved(id: string) {
    return cards.value.some((c) => c.id === id)
  }

  // F7: explicit, opt-in save. saving an already-saved pattern
  // just returns the existing card rather than duplicating it.
  function save(pattern: Pattern): SavedCard {
    const existing = cards.value.find((c) => c.id === pattern.id)
    if (existing) return existing

    const card: SavedCard = { ...pattern, savedAt: new Date().toISOString(), lastOpened: null }
    cards.value.unshift(card)
    return card
  }

  function touch(id: string) {
    const card = cards.value.find((c) => c.id === id)
    if (card) card.lastOpened = new Date().toISOString()
  }

  function clear() {
    cards.value = []
  }

  return { cards, sortedByNeglect, isSaved, save, touch, clear }
})
