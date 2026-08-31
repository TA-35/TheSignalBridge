<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useCardsStore } from '@/stores/cards'
import { describeLastOpened } from '@/utils/relativeTime'

const router = useRouter()
const store = useCardsStore()

const view = ref<'list' | 'deck'>('list')
const deckPos = ref(0)

function preview(text: string): string {
  return text.length > 118 ? `${text.slice(0, 116)}…` : text
}

const cards = computed(() =>
  store.sortedByNeglect.map((card) => ({
    ...card,
    meta: describeLastOpened(card.lastOpened),
    // A card with no library match has no explanation - show the message
    // it came from instead.
    impliesPreview: preview(card.implies ?? card.excerpt),
  })),
)

const deckCard = computed(() => (cards.value.length ? cards.value[deckPos.value % cards.value.length] : null))

function open(id: string) {
  router.push({ name: 'card-review', params: { id } })
}

function nextInDeck() {
  if (cards.value.length) deckPos.value = (deckPos.value + 1) % cards.value.length
}
</script>

<template>
  <div class="study">
    <div class="header">
      <div>
        <h2>Study</h2>
        <p>Explore whatever you feel like.</p>
      </div>
      <div class="tabs">
        <button type="button" class="tab" :class="{ 'tab--active': view === 'list' }" @click="view = 'list'">
          List
        </button>
        <button type="button" class="tab" :class="{ 'tab--active': view === 'deck' }" @click="view = 'deck'">
          Deck
        </button>
      </div>
    </div>

    <div v-if="!cards.length" class="empty">
      <strong>Nothing saved yet</strong>
      <p>Cards appear here when you choose to keep a pattern after reviewing a message.</p>
      <div class="empty-actions">
        <RouterLink to="/decode" class="btn btn--primary">Review a message</RouterLink>
        <RouterLink to="/library" class="btn btn--secondary">Browse the pattern library</RouterLink>
      </div>
    </div>

    <div v-else-if="view === 'list'" class="list">
      <button v-for="card in cards" :key="card.id" type="button" class="card-row" @click="open(card.id)">
        <span class="card-row__text">
          <strong>{{ card.name }}</strong>
          <span>{{ card.impliesPreview }}</span>
          <span class="meta">{{ card.meta }}</span>
        </span>
        <span class="explore">Explore -></span>
      </button>
    </div>

    <div v-else class="deck">
      <button v-if="deckCard" type="button" class="deck-card" @click="open(deckCard.id)">
        <strong>{{ deckCard.name }}</strong>
        <span>Tap to open · {{ deckCard.meta }}</span>
      </button>
      <div class="deck-controls">
        <button type="button" class="btn btn--secondary" @click="nextInDeck">Next card</button>
        <span class="meta">{{ cards.length }} in the pile</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.study {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.header h2 {
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.015em;
  margin: 0 0 6px;
}

.header p {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
}

.tabs {
  display: flex;
  gap: 2px;
  padding: 3px;
  background: #efeae1;
  border-radius: 999px;
}

.tab {
  padding: 7px 15px;
  border-radius: 999px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  background: transparent;
  color: var(--color-text-faint);
}

.tab--active {
  background: var(--color-frame);
  color: var(--color-text);
  box-shadow: 0 1px 2px rgba(58, 55, 51, 0.08);
}

.empty {
  border: 1px solid var(--color-border-soft);
  border-radius: 14px;
  background: var(--color-surface-soft);
  padding: 44px 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}

.empty strong {
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 500;
}

.empty p {
  margin: 0 0 6px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-muted);
  max-width: 340px;
}

.empty-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}

.btn {
  padding: 11px 18px;
  border-radius: 9px;
  font-size: 14px;
  cursor: pointer;
}

.btn--primary {
  border: 1px solid var(--color-primary-border);
  background: var(--color-primary);
  color: var(--color-frame);
}

.btn--secondary {
  border: 1px solid var(--color-border-strong);
  background: var(--color-frame);
  color: #4a453e;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.card-row {
  text-align: left;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 18px 20px;
  border: 1px solid var(--color-border-soft);
  border-radius: 12px;
  background: var(--color-surface);
  cursor: pointer;
}

.card-row:hover {
  border-color: var(--color-border-strong);
  background: var(--color-surface-soft);
}

.card-row__text {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.card-row__text strong {
  font-size: 15.5px;
  font-weight: 600;
  color: var(--color-text);
}

.card-row__text span {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.meta {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-faint) !important;
}

.explore {
  font-size: 13px;
  color: var(--color-primary);
  white-space: nowrap;
}

.deck {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 22px;
  padding: 16px 0 8px;
}

.deck-card {
  width: 100%;
  max-width: 460px;
  min-height: 200px;
  border: 1px solid var(--color-border-strong);
  border-radius: 14px;
  background: var(--color-surface);
  padding: 26px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-start;
  text-align: left;
  cursor: pointer;
  gap: 10px;
}

.deck-card strong {
  font-family: var(--font-serif);
  font-size: 23px;
  font-weight: 500;
  line-height: 1.25;
  color: var(--color-text);
}

.deck-card span {
  font-size: 13.5px;
  color: var(--color-text-muted);
}

.deck-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}
</style>
