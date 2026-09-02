<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getPatterns } from '@/services/patternsService'
import { useCardsStore } from '@/stores/cards'
import type { Pattern } from '@/types/pattern'

const router = useRouter()
const store = useCardsStore()

const patterns = ref<Pattern[]>([])
const loading = ref(true)
const activeTag = ref('All')

onMounted(async () => {
  patterns.value = await getPatterns()
  loading.value = false
})

const tags = computed(() => ['All', ...new Set(patterns.value.map((p) => p.category))])

const visible = computed(() =>
  patterns.value.filter((p) => activeTag.value === 'All' || p.category === activeTag.value),
)

function addToCards(pattern: Pattern) {
  store.savePattern(pattern)
}

function explore(pattern: Pattern) {
  // Route by the card's own id - a card is no longer identified by its pattern.
  const card = store.savePattern(pattern)
  router.push({ name: 'card-review', params: { id: card.id }, query: { from: 'library' } })
}
</script>

<template>
  <div class="library">
    <div class="header">
      <h2>Pattern library</h2>
      <p>Common workplace phrasings. Add any of them to your own cards.</p>
    </div>

    <div class="tags">
      <button
        v-for="tag in tags"
        :key="tag"
        type="button"
        class="tag"
        :class="{ 'tag--active': activeTag === tag }"
        @click="activeTag = tag"
      >
        {{ tag }}
      </button>
    </div>

    <p v-if="loading" class="status">Loading the pattern library…</p>

    <div v-else class="grid">
      <div v-for="item in visible" :key="item.id" class="item">
        <span class="item__tag">{{ item.category }}</span>
        <strong class="item__name">{{ item.name }}</strong>
        <span class="item__implies">{{ item.implies }}</span>
        <div class="item__actions">
          <button
            type="button"
            class="btn"
            :class="store.isPatternSaved(item.id) ? 'btn--saved' : 'btn--outline'"
            :disabled="store.isPatternSaved(item.id)"
            @click="addToCards(item)"
          >
            {{ store.isPatternSaved(item.id) ? 'Saved' : 'Add to my cards' }}
          </button>
          <button type="button" class="explore" @click="explore(item)">Explore -></button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.library {
  display: flex;
  flex-direction: column;
  gap: 20px;
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

.tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tag {
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid var(--color-border);
  background: var(--color-frame);
  color: var(--color-text-muted);
}

.tag--active {
  border-color: var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

.status {
  font-size: 14px;
  color: var(--color-text-muted);
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

.item {
  border: 1px solid var(--color-border-soft);
  border-radius: 12px;
  background: var(--color-surface);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.item__tag {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: var(--color-text-faint);
}

.item__name {
  font-size: 15.5px;
  font-weight: 600;
  color: var(--color-text);
}

.item__implies {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.item__actions {
  margin-top: auto;
  padding-top: 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.btn {
  padding: 8px 13px;
  border-radius: 8px;
  font-size: 12.5px;
  cursor: pointer;
}

.btn--outline {
  border: 1px solid var(--color-border-strong);
  background: var(--color-frame);
  color: #4a453e;
}

.btn--saved {
  border: 1px solid var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
  cursor: default;
}

.explore {
  background: none;
  border: none;
  padding: 0;
  font-size: 13px;
  color: var(--color-primary);
  cursor: pointer;
}
</style>
