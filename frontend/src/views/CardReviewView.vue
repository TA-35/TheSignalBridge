<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCardsStore } from '@/stores/cards'
import { getPatterns } from '@/services/patternsService'
import type { Pattern } from '@/types/pattern'

const route = useRoute()
const router = useRouter()
const store = useCardsStore()

const flipped = ref(false)
const patterns = ref<Pattern[]>([])

// Library links here to preview a pattern that may not be saved yet; Study
// links here to open a card the user already chose to keep. Same page, two
// very different data sources - a preview must never write to the store.
const isPreview = computed(() => route.name === 'pattern-preview')

onMounted(async () => {
  if (isPreview.value) patterns.value = await getPatterns()
})

const previewPattern = computed(() => patterns.value.find((p) => p.id === route.params.patternId))
const savedCard = computed(() => store.cards.find((c) => c.id === route.params.id))

const card = computed(() => {
  if (!isPreview.value) return savedCard.value
  const p = previewPattern.value
  if (!p) return undefined
  return {
    category: p.category,
    name: p.name,
    excerpt: '',
    implies: p.implies,
    why_misread: p.why_misread,
    unsaid: [] as { field: string; prompt: string }[],
  }
})

const alreadySaved = computed(() => (previewPattern.value ? store.isPatternSaved(previewPattern.value.id) : false))

const orderedIds = computed(() =>
  isPreview.value ? patterns.value.map((p) => p.id) : store.sortedByNeglect.map((c) => c.id),
)
const currentId = computed(() => (isPreview.value ? (route.params.patternId as string) : (route.params.id as string)))
const index = computed(() => orderedIds.value.indexOf(currentId.value))

const backTo = computed(() => (isPreview.value ? '/library' : '/study'))
const backLabel = computed(() => (isPreview.value ? '← Back to Library' : '← Back to Study'))

watch(
  currentId,
  (id) => {
    flipped.value = false
    if (!isPreview.value && typeof id === 'string') store.touch(id)
  },
  { immediate: true },
)

function step(delta: number) {
  const ids = orderedIds.value
  if (!ids.length || index.value < 0) return
  const next = (index.value + delta + ids.length) % ids.length
  if (isPreview.value) {
    router.push({ name: 'pattern-preview', params: { patternId: ids[next] } })
  } else {
    router.push({ name: 'card-review', params: { id: ids[next] } })
  }
}

function saveToStudy() {
  if (previewPattern.value) store.savePattern(previewPattern.value)
}
</script>

<template>
  <div v-if="card" class="review">
    <div class="topline">
      <RouterLink :to="backTo" class="back">{{ backLabel }}</RouterLink>
      <span class="pos">card {{ index + 1 }} of {{ orderedIds.length }}</span>
    </div>

    <div class="card">
      <span v-if="card.category" class="tag">{{ card.category }}</span>
      <strong class="name">{{ card.name }}</strong>

      <p v-if="card.excerpt" class="excerpt">{{ card.excerpt }}</p>

      <div class="reveal" :class="{ 'reveal--open': flipped }">
        <div class="reveal__inner">
          <template v-if="card.implies">
            <div class="block">
              <span class="block__label">What this phrasing usually implies</span>
              <span class="block__text">{{ card.implies }}</span>
            </div>
            <div class="rule" />
            <div class="block">
              <span class="block__label">Why it tends to get misread</span>
              <span class="block__text">{{ card.why_misread }}</span>
            </div>
          </template>

          <!-- No library match: what the message left unsaid is the lesson. -->
          <div v-if="card.unsaid.length" class="block">
            <div v-if="card.implies" class="rule" />
            <span class="block__label">What this message left unsaid</span>
            <ul class="unsaid">
              <li v-for="gap in card.unsaid" :key="gap.field">{{ gap.prompt }}</li>
            </ul>
          </div>

          <div v-if="!card.implies && !card.unsaid.length" class="block">
            <span class="block__text">This one stated everything it needed to.</span>
          </div>
        </div>
      </div>
    </div>

    <div class="controls">
      <button type="button" class="btn btn--secondary" @click="step(-1)">Previous</button>
      <button type="button" class="btn btn--primary flip" @click="flipped = !flipped">
        {{ flipped ? "That's enough for now" : 'Explore this idea' }}
      </button>
      <button type="button" class="btn btn--secondary" @click="step(1)">Next</button>
    </div>

    <button
      v-if="isPreview"
      type="button"
      class="btn save-to-study"
      :class="alreadySaved ? 'btn--saved' : 'btn--outline'"
      :disabled="alreadySaved"
      @click="saveToStudy"
    >
      {{ alreadySaved ? 'Saved to Study ✓' : 'Save to Study' }}
    </button>
  </div>
</template>

<style scoped>
.review {
  display: flex;
  flex-direction: column;
  gap: 20px;
  align-items: center;
}

.topline {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.back {
  font-size: 13.5px;
  color: var(--color-primary);
}

.pos {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--color-text-faint);
}

.card {
  width: 100%;
  max-width: 560px;
  border: 1px solid var(--color-border-strong);
  border-radius: 16px;
  background: var(--color-surface);
  padding: 30px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.tag {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.09em;
  color: var(--color-text-faint);
}

.name {
  font-family: var(--font-serif);
  font-size: 28px;
  font-weight: 500;
  line-height: 1.22;
  letter-spacing: -0.015em;
  color: var(--color-text);
}

.reveal {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 300ms ease-out;
}

.reveal--open {
  grid-template-rows: 1fr;
}

.reveal__inner {
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.reveal--open .reveal__inner {
  padding-top: 18px;
  border-top: 1px solid var(--color-border-soft);
}

.block {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.block__label {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.09em;
  color: #8ca79a;
}

.block__text {
  font-size: 15px;
  line-height: 1.66;
  color: var(--color-text);
}

.rule {
  height: 1px;
  background: #e5ede9;
}

.controls {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: center;
}

.btn {
  padding: 11px 16px;
  border-radius: 9px;
  font-size: 13.5px;
  cursor: pointer;
}

.btn--secondary {
  border: 1px solid var(--color-border-strong);
  background: var(--color-frame);
  color: #4a453e;
}

.btn--primary {
  border: 1px solid var(--color-primary-border);
  background: var(--color-primary);
  color: var(--color-frame);
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

.save-to-study {
  padding: 11px 20px;
  font-weight: 500;
}

.flip {
  width: 200px;
  padding: 12px 24px;
  font-size: 14.5px;
  font-weight: 500;
  text-align: center;
}

@media (prefers-reduced-motion: reduce) {
  .reveal {
    transition: none;
  }
}

.excerpt {
  margin: 12px 0 0;
  font-style: italic;
  opacity: 0.78;
  line-height: 1.5;
}

.unsaid {
  margin: 6px 0 0;
  padding-left: 18px;
}

.unsaid li {
  margin-bottom: 4px;
}
</style>
