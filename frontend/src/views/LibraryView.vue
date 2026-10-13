<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search, X } from '@lucide/vue'
import PageNav from '@/components/PageNav.vue'
import CategoryArt from '@/components/library/CategoryArt.vue'
import { categoryHue } from '@/utils/categories'
import { getPatterns } from '@/services/patternsService'
import { useCardsStore } from '@/stores/cards'
import { useActivityStore } from '@/stores/activity'
import type { Pattern } from '@/types/pattern'

const router = useRouter()
const route = useRoute()
const store = useCardsStore()
const activity = useActivityStore()

const patterns = ref<Pattern[]>([])
const loading = ref(true)

onMounted(async () => {
  patterns.value = await getPatterns()
  loading.value = false
})

// Category isn't part of the Pattern record's own metadata - these six are
// the fixed enum from docs/api-contract.md, so a one-line blurb per category
// is safe to hand-write here rather than fetched. Each category's colour and
// drawing live in utils/categories.ts and components/library/CategoryArt.vue.
const CATEGORY_BLURB: Record<string, string> = {
  'Softened request': 'Politely worded, but still a real ask.',
  'Vague deadline': 'A time is implied, just never stated.',
  'Unassigned owner': "Someone is expected to own this, but it doesn't say who.",
  'Feedback framing': 'Praise softening a note that matters more than it sounds.',
  'Unclear priority': 'How urgent this really is, left for you to guess.',
  'Undefined scope': 'The size of the ask is narrower than the wording suggests.',
}

const categories = computed(() => {
  const counts = new Map<string, number>()
  for (const p of patterns.value) counts.set(p.category, (counts.get(p.category) ?? 0) + 1)
  return [...counts.entries()].map(([name, count]) => ({
    name,
    count,
    blurb: CATEGORY_BLURB[name] ?? '',
  }))
})

const activeBlurb = computed(() => (activeCategory.value ? (CATEGORY_BLURB[activeCategory.value] ?? '') : ''))

// The card and pill pick up their category's colour through one CSS variable;
// the soft background and text colour are mixed from it in the styles below.
const hueStyle = (category: string | null | undefined) => ({ '--cat': categoryHue(category) })

// Lives in the query string, not a route param, so it never collides with
// /library/:patternId (the preview route) - and so a category is
// bookmarkable/shareable and survives the back button.
const activeCategory = computed(() => (typeof route.query.category === 'string' ? route.query.category : null))

function selectCategory(name: string | null) {
  searchQuery.value = ''
  router.push({ query: { ...route.query, category: name ?? undefined } })
}

// A typed search takes over from category browsing - it looks across every
// category by phrase name, not just the one currently selected, since the
// point is finding a specific phrase without knowing where it lives.
const searchQuery = ref('')
const isSearching = computed(() => searchQuery.value.trim().length > 0)

const visible = computed(() => {
  if (isSearching.value) {
    const q = searchQuery.value.trim().toLowerCase()
    return patterns.value.filter((p) => p.name.toLowerCase().includes(q))
  }
  // No category selected is "Overview", and Overview now shows everything.
  // It used to return [], so the sidebar highlighted Overview as the current
  // item while the pane said "Pick a category to start" - the nav claiming a
  // choice had been made and the content denying it.
  return activeCategory.value ? patterns.value.filter((p) => p.category === activeCategory.value) : patterns.value
})

// Six a page. The library is 60 cards now, and Overview used to put all of
// them on one scroll - which buries the category filters under a wall of
// phrases and makes "where was that one" a scrolling problem.
const PAGE_SIZE = 6
const page = ref(1)

const pageCount = computed(() => Math.max(1, Math.ceil(visible.value.length / PAGE_SIZE)))
const pageItems = computed(() => visible.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

const rangeLabel = computed(() => {
  const total = visible.value.length
  if (!total) return ''
  const first = (page.value - 1) * PAGE_SIZE + 1
  const last = Math.min(page.value * PAGE_SIZE, total)
  return `Showing ${first}–${last} of ${total} phrase${total === 1 ? '' : 's'}`
})

// Switching category or typing a search starts a new list, so page 1 is the
// only honest place to be. Watching `visible` rather than the two inputs
// catches the patterns arriving from the API too.
watch(visible, () => {
  page.value = 1
})

// A category with fewer cards can leave the reader on a page past the end.
watch(pageCount, (count) => {
  if (page.value > count) page.value = count
})

function addToCards(pattern: Pattern) {
  store.savePattern(pattern)
}

function explore(pattern: Pattern) {
  // counts as "opened" on the progress dashboard
  activity.markViewed(pattern.id)
  // Preview only - saving is an explicit choice made on the detail page.
  // Carries the category along so "back" and paging stay inside it - but
  // not while searching, since results there can span every category.
  router.push({
    name: 'pattern-preview',
    params: { patternId: pattern.id },
    query: !isSearching.value && activeCategory.value ? { category: activeCategory.value } : {},
  })
}
</script>

<template>
  <div class="library">
    <div class="header">
      <h1>Pattern library</h1>
      <p>Common phrases, and what they actually mean.</p>
    </div>

    <div class="search">
      <Search :size="16" :stroke-width="2" class="search__icon" aria-hidden="true" />
      <input
        v-model="searchQuery"
        type="search"
        class="search__input"
        placeholder="Search by phrase…"
        aria-label="Search the pattern library by phrase"
      />
      <button v-if="searchQuery" type="button" class="search__clear" aria-label="Clear search" @click="searchQuery = ''">
        <X :size="15" :stroke-width="2" aria-hidden="true" />
      </button>
    </div>

    <p v-if="loading" class="status">Loading the pattern library…</p>

    <template v-else>
      <!-- Filter pills replace the old sidebar: all six categories are visible at
           every width, and each carries its colour so the cards below are easy
           to match to it. Colour is never the only signal - every pill has
           its name and count. -->
      <div class="filters" role="group" aria-label="Filter patterns by category">
        <button
          type="button"
          class="pill pill--all"
          :aria-pressed="!activeCategory"
          @click="selectCategory(null)"
        >
          All <span class="pill__count">{{ patterns.length }}</span>
        </button>
        <button
          v-for="cat in categories"
          :key="cat.name"
          type="button"
          class="pill"
          :style="hueStyle(cat.name)"
          :aria-pressed="activeCategory === cat.name"
          @click="selectCategory(cat.name)"
        >
          <span class="pill__dot" aria-hidden="true"></span>
          {{ cat.name }} <span class="pill__count">{{ cat.count }}</span>
        </button>
      </div>

      <div v-if="activeCategory && !isSearching" class="category-intro" :style="hueStyle(activeCategory)">
        <CategoryArt :category="activeCategory" :size="40" class="category-intro__art" />
        <p>{{ activeBlurb }}</p>
      </div>

      <div class="content">
        <div v-if="!visible.length && !isSearching" class="intro">
          <strong>No patterns yet</strong>
          <p>The library could not be loaded. Try again in a moment.</p>
        </div>

        <p v-else-if="isSearching && !visible.length" class="status">No phrases match "{{ searchQuery }}".</p>

        <div v-else class="grid">
          <div v-for="item in pageItems" :key="item.id" class="item" :style="hueStyle(item.category)" @click="explore(item)">
            <!-- The coloured band and drawing say which category this is at a
                 glance. The written tag stays in "All" and in search results,
                 where cards genuinely span categories; inside one category it
                 would only repeat the pill just clicked. -->
            <div class="item__band">
              <span v-if="!activeCategory || isSearching" class="item__tag">{{ item.category }}</span>
              <CategoryArt :category="item.category" :size="52" class="item__art" />
            </div>
            <div class="item__body">
              <strong class="item__name">{{ item.name }}</strong>
              <div class="item__actions">
                <button type="button" class="explore" @click.stop="explore(item)">See what this means</button>
                <button
                  type="button"
                  class="btn"
                  :class="store.isPatternSaved(item.id) ? 'btn--saved' : 'btn--outline'"
                  :disabled="store.isPatternSaved(item.id)"
                  @click.stop="addToCards(item)"
                >
                  {{ store.isPatternSaved(item.id) ? 'Saved' : 'Add to my cards' }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <PageNav
          v-if="visible.length"
          v-model:page="page"
          class="pager"
          :page-count="pageCount"
          :label="rangeLabel"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.library {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 60ch;
}

.header h1 {
  font-family: var(--font-serif);
  font-size: clamp(32px, 4.4vw, 46px);
  font-weight: 500;
  line-height: 1.08;
  letter-spacing: -0.025em;
  margin: 0;
  text-wrap: balance;
}

.header p {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.search {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-frame);
}

.search:focus-within {
  border-color: var(--color-primary);
}

.search__icon {
  flex: 0 0 auto;
  color: var(--color-text-faint);
}

.search__input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: none;
  padding: 11px 0;
  font-size: 14px;
  color: var(--color-text);
}

.search__clear {
  flex: 0 0 auto;
  display: flex;
  padding: 4px;
  border: none;
  background: none;
  color: var(--color-text-faint);
  cursor: pointer;
}

.search__clear:hover {
  color: var(--color-text);
}

.status {
  font-size: 14px;
  color: var(--color-text-muted);
}

/* Filter pills ---------------------------------------------------------
   Each pill and card sets --cat (its category's hue) inline. The soft fill
   and the text colour are mixed from it against the theme's own surface and
   text colours, so they darken in dark mode on their own and keep their
   contrast: text is pulled towards --color-text, fills towards the surface.
   60% hue in the text keeps every category at 4.5:1 or more on its soft fill
   in all four accents, light and dark (72% let six of them slip under). */
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pill {
  --cat: var(--color-primary);
  --cat-ink: color-mix(in srgb, var(--cat) 60%, var(--color-text));
  --cat-soft: color-mix(in srgb, var(--cat) 16%, var(--color-surface));
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-surface);
  font-size: 13.5px;
  color: var(--color-text);
  cursor: pointer;
}

.pill:hover {
  border-color: var(--cat-ink);
}

.pill[aria-pressed='true'] {
  border-color: var(--cat-ink);
  background: var(--cat-soft);
  color: var(--cat-ink);
  font-weight: 600;
}

.pill--all[aria-pressed='true'] {
  border-color: var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

.pill__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--cat);
  flex: 0 0 auto;
}

.pill__count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-muted);
}

.pill[aria-pressed='true'] .pill__count {
  color: inherit;
}

.category-intro {
  --cat-ink: color-mix(in srgb, var(--cat) 60%, var(--color-text));
  --cat-soft: color-mix(in srgb, var(--cat) 16%, var(--color-surface));
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  background: var(--cat-soft);
  color: var(--cat-ink);
}

.category-intro p {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.5;
}

.category-intro__art {
  flex: 0 0 auto;
}

.content {
  min-width: 0;
}

/* Solid, like every other surface in the app. The dashed border was the only
   one on the site and read as an unfinished placeholder. */
.intro {
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface-soft);
  padding: 40px 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 10px;
}

.intro p {
  margin: 0;
  max-width: 420px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

@media (max-width: 1080px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* Cards --------------------------------------------------------------------- */
.item {
  --cat: var(--color-text-muted);
  --cat-ink: color-mix(in srgb, var(--cat) 60%, var(--color-text));
  --cat-soft: color-mix(in srgb, var(--cat) 16%, var(--color-surface));
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  cursor: pointer;
}

.item:hover {
  border-color: var(--cat-ink);
}

.item__band {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  min-height: 52px;
  padding: 14px 16px;
  background: var(--cat-soft);
  color: var(--cat-ink);
}

.item__art {
  flex: 0 0 auto;
  margin-left: auto;
}

/* 10.5px on --color-text-faint was 3.5:1 and under the 11px floor. The tag
   now takes its category's text colour, which is mixed towards --color-text
   so it stays readable on the band. */
.item__tag {
  font-family: var(--font-mono);
  font-size: 11.5px;
  letter-spacing: 0.08em;
  color: var(--cat-ink);
}

.item__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

.item__name {
  font-size: 15.5px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--color-text);
}

.item__actions {
  margin-top: auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.btn {
  padding: 8px 13px;
  border-radius: 8px;
  font-size: 12.5px;
  cursor: pointer;
}

/* The main action, filled with the category's colour. Its text is the page
   surface colour: light on a dark fill in light mode, dark on a light fill in
   dark mode. */
.explore {
  padding: 8px 13px;
  border-radius: 8px;
  border: 1px solid var(--cat-ink);
  background: var(--cat-ink);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-surface);
  cursor: pointer;
  white-space: nowrap;
}

.explore:hover {
  filter: brightness(1.08);
}

.pager {
  margin-top: 18px;
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: 1fr;
  }

  /* Seven pills wrapping on a phone is seven rows: the first card ends up
     below the fold, so the page opens on filters rather than on content -
     the opposite of what the sidebar was replaced to achieve. One scrolling
     strip keeps every category reachable and costs one row.

     Not a dropdown: the counts and the category colours are the thing that
     makes a card easy to match back to its filter, and a collapsed control
     hides both. A partly visible pill at the right edge is the affordance. */
  .filters {
    flex-wrap: nowrap;
    overflow-x: auto;
    /* Room for the focus ring, which would otherwise be clipped by the
       scroll container on the row above and below. */
    padding: 3px 0;
    scroll-snap-type: x proximity;
    /* The strip is scrolled by swiping or by tabbing through the pills, so
       the bar itself is noise on a phone. */
    scrollbar-width: none;
  }

  .filters::-webkit-scrollbar {
    display: none;
  }

  .pill {
    /* Without this they shrink to fit instead of overflowing, and the labels
       wrap to two lines each. */
    flex: 0 0 auto;
    scroll-snap-align: start;
  }
}
</style>
