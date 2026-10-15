<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Check } from '@lucide/vue'
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

// Came in from a specific category's list (Library's sidebar) - paging and
// "back" should stay inside that category, not jump across the whole set.
const previewCategory = computed(() => (typeof route.query.category === 'string' ? route.query.category : null))

const orderedIds = computed(() => {
  if (!isPreview.value) return store.sortedByNeglect.map((c) => c.id)
  const pool = previewCategory.value
    ? patterns.value.filter((p) => p.category === previewCategory.value)
    : patterns.value
  return pool.map((p) => p.id)
})
const currentId = computed(() => (isPreview.value ? (route.params.patternId as string) : (route.params.id as string)))
const index = computed(() => orderedIds.value.indexOf(currentId.value))

const backTo = computed(() =>
  isPreview.value ? { path: '/library', query: previewCategory.value ? { category: previewCategory.value } : {} } : '/study',
)
// The arrow is an <ArrowLeft> beside this, not a character inside it: the rest
// of the app draws its icons with Lucide, and Study was using an ASCII "->"
// for the same job.
const backLabel = computed(() => (isPreview.value ? 'Back to Library' : 'Back to Study'))

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
    router.push({
      name: 'pattern-preview',
      params: { patternId: ids[next] },
      query: previewCategory.value ? { category: previewCategory.value } : {},
    })
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
      <RouterLink :to="backTo" class="back">
        <ArrowLeft :size="15" :stroke-width="2" aria-hidden="true" />
        {{ backLabel }}
      </RouterLink>
      <span class="pos">card {{ index + 1 }} of {{ orderedIds.length }}</span>
    </div>

    <div class="card">
      <span v-if="card.category" class="tag">{{ card.category }}</span>
      <!-- The phrase being studied is what this page is about, so it is the
           page's heading. This screen previously had no heading element at
           all, which left a screen reader nothing to navigate by. -->
      <h1 class="name">{{ card.name }}</h1>

      <p v-if="card.excerpt" class="excerpt">{{ card.excerpt }}</p>

      <div id="card-reveal" class="reveal" :class="{ 'reveal--open': flipped }">
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
      <button
        type="button"
        class="btn btn--primary flip"
        :aria-expanded="flipped"
        aria-controls="card-reveal"
        @click="flipped = !flipped"
      >
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
      <Check v-if="alreadySaved" :size="14" :stroke-width="2" aria-hidden="true" />
      {{ alreadySaved ? 'Saved to Study' : 'Save to Study' }}
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

/* Was 13.5px on --color-primary: 4.05:1, just under the 4.5:1 this size
   needs. The strong variant of the same hue clears it at 7.7:1. The padding
   is what takes the target from 18px tall to a reachable one. */
.back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 0;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--color-primary-strong-text);
}

/* --color-text-faint measures 2.96:1 on the page background. It is never a
   safe colour for text at any size this app uses. */
.pos {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-muted);
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
  font-size: 11.5px;
  letter-spacing: 0.09em;
  color: var(--color-text-muted);
}

/* An <h1> now, so it arrives with the browser's own heading margins. */
.name {
  margin: 0;
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

/* The worst text on the site before this: 10.5px at 2.55:1, on the two labels
   that say what you are reading. Below the 11px floor as well as the contrast
   one, and hardcoded to a light-mode green so dark mode never touched it. */
.block__label {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.09em;
  color: var(--color-primary-strong-text);
}

.block__text {
  font-size: 15px;
  line-height: 1.66;
  color: var(--color-text);
}

.rule {
  height: 1px;
  background: var(--color-border-soft);
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

.save-to-study {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 11px 20px;
  font-weight: 500;
}

/* Previous and Next share one width so the primary button sits on the card's
   centre line - "Previous" is wider than "Next", which pushed it right. */
.controls .btn--secondary {
  width: 112px;
}

/* Wide enough for both labels on one line, so the button keeps one size when
   it flips. At 200px "That's enough for now" wrapped and grew taller. */
.flip {
  min-width: 224px;
  padding: 12px 24px;
  font-size: 14.5px;
  font-weight: 500;
  text-align: center;
  white-space: nowrap;
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

/* Narrow screens: the three controls do not fit on one line. `.flip` is at
   least 224px and each side button 112px, so the row needs ~448px before
   gaps - more than a 360px phone has. Left to wrap, "Previous" lands alone on the first row and
   the primary action ends up beside Next, which reads as two unrelated pairs.
   So give the primary action its own full-width row and let Previous and Next
   share the one below.

   This block sits at the end of the file on purpose: a media query does not
   raise specificity, so any base rule written below it would win at the same
   specificity and silently undo it. */
@media (max-width: 560px) {
  .controls {
    /* .review centres its children, so .controls is content-width by default
       and a percentage inside it would resolve against nothing useful. */
    width: 100%;
    gap: 8px;
  }

  .flip {
    width: 100%;
    /* Before the other two, not after - the thing you came to do should not be
       the third button you read. */
    order: -1;
  }

  .controls .btn--secondary {
    /* Equal halves of the second row, whatever the label lengths. */
    flex: 1 1 0;
    min-width: 0;
  }

  .save-to-study {
    width: 100%;
  }
}
</style>
