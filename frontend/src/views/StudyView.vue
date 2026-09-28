<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useCardsStore } from '@/stores/cards'
import { describeLastOpened } from '@/utils/relativeTime'

const router = useRouter()
const store = useCardsStore()

function preview(text: string): string {
  return text.length > 64 ? `${text.slice(0, 62)}…` : text
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

function open(id: string) {
  router.push({ name: 'card-review', params: { id } })
}

</script>

<template>
  <div class="study">
    <div class="header">
      <h1>Study</h1>
      <p>Cards you've kept from the library and from messages you've reviewed. Open one to refresh what it means.</p>
    </div>

    <div v-if="!cards.length" class="empty">
      <strong>Nothing saved yet</strong>
      <p>Cards appear here when you choose to keep a pattern after reviewing a message.</p>
      <div class="empty-actions">
        <RouterLink to="/decode" class="btn btn--primary">Decode a message</RouterLink>
        <RouterLink to="/library" class="btn btn--secondary">Browse the pattern library</RouterLink>
      </div>
    </div>

    <div v-else class="list">
      <button v-for="card in cards" :key="card.id" type="button" class="card-row" @click="open(card.id)">
        <span class="card-row__text">
          <strong>{{ card.name }}</strong>
          <span class="meta">{{ card.meta }}</span>
        </span>
        <!-- A cue, not a control. This was a bordered, filled pill reading
             "See more ->" sitting INSIDE the row's own <button>, so it looked
             like the thing to click when the whole row already was. The label
             also now matches the Library's wording for the same destination. -->
        <span class="explore">
          See what this means
          <ChevronRight :size="15" :stroke-width="2" aria-hidden="true" />
        </span>
      </button>
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
  flex-direction: column;
}

.header h1 {
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

/* --color-text-faint is 3.5:1 on the card surface and 2.96:1 on the page.
   The !important was there to win against a parent rule, not to pick this
   colour, so it survives the swap. */
.meta {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--color-text-muted) !important;
}

.explore {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary-strong-text);
  white-space: nowrap;
}

.card-row:hover .explore {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.card-row:hover .explore {
  border-color: var(--color-primary-border);
}

</style>
