import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { Pattern, SavedCard } from '@/types/pattern'
import type { DecodeRecord } from '@/types/decode'
import { fetchCards, pushCard, removeCard } from '@/services/cardSyncService'
import { getPatterns } from '@/services/patternsService'
import { useAccountStore } from '@/stores/account'

const STORAGE_KEY = 'readtheroom.cards'

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `c_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
}

// Cards saved before cards became records of an encounter were the library row
// itself, spread flat. Carry them forward rather than dropping someone's deck;
// they have no decode to point back at.
function migrate(raw: unknown): SavedCard[] {
  if (!Array.isArray(raw)) return []

  return raw.map((item: Record<string, unknown>): SavedCard => {
    if ('decodeId' in item) return item as unknown as SavedCard

    return {
      id: newId(),
      decodeId: null,
      patternId: (item.id as string) ?? null,
      name: (item.name as string) ?? 'Saved card',
      category: (item.category as string) ?? null,
      implies: (item.implies as string) ?? null,
      why_misread: (item.why_misread as string) ?? null,
      excerpt: '',
      unsaid: [],
      savedAt: (item.savedAt as string) ?? new Date().toISOString(),
      lastOpened: (item.lastOpened as string) ?? null,
    }
  })
}

function load(): SavedCard[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? migrate(JSON.parse(raw)) : []
  } catch {
    return []
  }
}

// The message, collapsed to one line, for the card front.
function toExcerpt(message: string, limit = 240): string {
  const flat = message.replace(/\s+/g, ' ').trim()
  return flat.length > limit ? `${flat.slice(0, limit - 1)}…` : flat
}

// A card with no library match still needs a title. The first ask is the most
// recognisable thing in the message; the excerpt is the fallback.
function deriveName(record: DecodeRecord): string {
  const first = record.tasks[0]?.text ?? toExcerpt(record.message, 60)
  const trimmed = first.trim()
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
}

// Saved cards never leave the browser, see docs/api-contract.md "Data
// retention". Settings' "clear" wipes these and the decodes behind them.
export const useCardsStore = defineStore('cards', () => {
  const cards = ref<SavedCard[]>(load())

  watch(
    cards,
    (value) => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
      } catch {
        // Quota or blocked storage: keep this session's cards in memory.
      }
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

  // One card per decode - two different messages that trip the same pattern
  // are two different encounters, and each is worth keeping.
  function isSaved(decodeId: string) {
    return cards.value.some((c) => c.decodeId === decodeId)
  }

  // Library saves are per pattern, not per encounter: adding the same row
  // twice from the library would just be a duplicate.
  function isPatternSaved(patternId: string) {
    return cards.value.some((c) => c.patternId === patternId)
  }

  // F7: explicit, opt-in save. `pattern` is null when the wording matched
  // nothing in the library; the card is still saved, carrying the message
  // and what it left unsaid.
  function save(record: DecodeRecord, pattern: Pattern | null): SavedCard {
    const existing = cards.value.find((c) => c.decodeId === record.id)
    if (existing) return existing

    const card: SavedCard = {
      id: newId(),
      decodeId: record.id,
      patternId: pattern?.id ?? null,
      name: pattern?.name ?? deriveName(record),
      category: pattern?.category ?? record.category,
      implies: pattern?.implies ?? null,
      why_misread: pattern?.why_misread ?? null,
      excerpt: toExcerpt(record.message),
      unsaid: record.missing.map((m) => ({ field: m.field, prompt: m.prompt })),
      savedAt: new Date().toISOString(),
      lastOpened: null,
    }
    cards.value.unshift(card)
    return card
  }

  // Saving straight from the library - no message behind it, so the card
  // carries the pattern only.
  function savePattern(pattern: Pattern): SavedCard {
    const existing = cards.value.find((c) => c.patternId === pattern.id)
    if (existing) return existing

    const card: SavedCard = {
      id: newId(),
      decodeId: null,
      patternId: pattern.id,
      name: pattern.name,
      category: pattern.category,
      implies: pattern.implies,
      why_misread: pattern.why_misread,
      excerpt: '',
      unsaid: [],
      savedAt: new Date().toISOString(),
      lastOpened: null,
    }
    cards.value.unshift(card)
    void push(card)
    return card
  }

  function touch(id: string) {
    const card = cards.value.find((c) => c.id === id)
    if (!card) return
    card.lastOpened = new Date().toISOString()
    void push(card)
  }

  function remove(id: string) {
    const card = cards.value.find((c) => c.id === id)
    cards.value = cards.value.filter((c) => c.id !== id)
    // Only library cards were ever on the server, so only they need
    // removing from it.
    if (card && syncable(card)) void removeCard(card.patternId as string)
  }

  function clear() {
    const synced = cards.value.filter(syncable)
    cards.value = []
    for (const card of synced) void removeCard(card.patternId as string)
  }

  // --- Syncing ----------------------------------------------------------
  //
  // A card syncs only if it came from the library: `decodeId === null` and
  // it names a pattern. A card made from a decode carries an excerpt of the
  // reader's own message, and that never leaves the browser - which is also
  // why a second device shows library cards and not those.

  function syncable(card: SavedCard): boolean {
    return card.decodeId === null && !!card.patternId
  }

  function push(card: SavedCard): Promise<void> {
    if (!useAccountStore().signedIn || !syncable(card)) return Promise.resolve()
    return pushCard(card.patternId as string, {
      saved_at: card.savedAt,
      last_opened_at: card.lastOpened,
    })
  }

  /**
   * Called when an account signs in, on whichever device.
   *
   * Both directions, because either side can be the one with news: a card
   * kept here while signed out has to reach the server, and a card kept on
   * another device has to be rebuilt here. Rebuilt, not downloaded - the
   * server stores a pattern id, and the pattern's text comes from
   * /api/patterns like any other library row.
   */
  async function syncWithAccount(): Promise<void> {
    if (!useAccountStore().signedIn) return

    const remote = await fetchCards()
    const remoteById = new Map(remote.map((row) => [row.pattern_id, row]))

    // Anything kept here that the server has not seen.
    for (const card of cards.value.filter(syncable)) {
      const row = remoteById.get(card.patternId as string)
      if (!row) {
        await push(card)
        continue
      }
      // Both sides know the card: keep whichever open is later.
      if (row.last_opened_at && (!card.lastOpened || row.last_opened_at > card.lastOpened)) {
        card.lastOpened = row.last_opened_at
      } else if (card.lastOpened && card.lastOpened !== row.last_opened_at) {
        await push(card)
      }
    }

    // Anything the server knows that this device does not.
    const missing = remote.filter(
      (row) => !cards.value.some((c) => c.patternId === row.pattern_id),
    )
    if (!missing.length) return

    const patterns = await getPatterns()
    for (const row of missing) {
      const pattern = patterns.find((p) => p.id === row.pattern_id)
      // A pattern that no longer exists in the library leaves its row on
      // the server rather than becoming a card with no content.
      if (!pattern) continue
      cards.value.push({
        id: newId(),
        decodeId: null,
        patternId: pattern.id,
        name: pattern.name,
        category: pattern.category,
        implies: pattern.implies,
        why_misread: pattern.why_misread,
        excerpt: '',
        unsaid: [],
        savedAt: row.saved_at ?? new Date().toISOString(),
        lastOpened: row.last_opened_at,
      })
    }
  }

  return {
    cards,
    sortedByNeglect,
    isSaved,
    isPatternSaved,
    save,
    savePattern,
    touch,
    remove,
    clear,
    syncWithAccount,
  }
})
