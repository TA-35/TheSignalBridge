<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  CalendarClock,
  Compass,
  MessageCircleQuestion,
  MessageSquareText,
  Search,
  Shapes,
  SlidersHorizontal,
  UserRoundX,
  X,
  type LucideIcon,
} from '@lucide/vue'
import { getPatterns } from '@/services/patternsService'
import { useCardsStore } from '@/stores/cards'
import type { Pattern } from '@/types/pattern'

const router = useRouter()
const route = useRoute()
const store = useCardsStore()

const patterns = ref<Pattern[]>([])
const loading = ref(true)

onMounted(async () => {
  patterns.value = await getPatterns()
  loading.value = false
})

// Category isn't part of the Pattern record's own metadata - these six are
// the fixed enum from docs/api-contract.md, so an icon + one-line blurb per
// category is safe to hand-write here rather than fetched.
const CATEGORY_INFO: Record<string, { icon: LucideIcon; blurb: string }> = {
  'Softened request': { icon: MessageCircleQuestion, blurb: 'Politely worded, but still a real ask.' },
  'Vague deadline': { icon: CalendarClock, blurb: 'A time is implied, just never stated.' },
  'Unassigned owner': { icon: UserRoundX, blurb: "Someone's expected to own this - it just doesn't say who." },
  'Feedback framing': { icon: MessageSquareText, blurb: 'Praise softening a note that matters more than it sounds.' },
  'Unclear priority': { icon: SlidersHorizontal, blurb: 'How urgent this really is, left for you to guess.' },
  'Undefined scope': { icon: Shapes, blurb: 'The size of the ask is narrower than the wording suggests.' },
}

const categories = computed(() => {
  const counts = new Map<string, number>()
  for (const p of patterns.value) counts.set(p.category, (counts.get(p.category) ?? 0) + 1)
  return [...counts.entries()].map(([name, count]) => ({
    name,
    count,
    icon: CATEGORY_INFO[name]?.icon ?? Compass,
    blurb: CATEGORY_INFO[name]?.blurb ?? '',
  }))
})

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

function addToCards(pattern: Pattern) {
  store.savePattern(pattern)
}

function explore(pattern: Pattern) {
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

    <!-- The sidebar's counterpart below 860px, where it is the only way to
         change category - so it needs the name the sidebar gets from being a
         labelled <nav>. -->
    <select
      class="category-select"
      aria-label="Filter patterns by category"
      :value="activeCategory ?? ''"
      @change="selectCategory(($event.target as HTMLSelectElement).value || null)"
    >
      <option value="">Overview</option>
      <option v-for="cat in categories" :key="cat.name" :value="cat.name">{{ cat.name }} ({{ cat.count }})</option>
    </select>

    <p v-if="loading" class="status">Loading the pattern library…</p>

    <div v-else class="layout">
      <nav class="sidebar" aria-label="Pattern categories">
        <button
          type="button"
          class="sidebar-item"
          :class="{ 'sidebar-item--active': !activeCategory }"
          :aria-current="!activeCategory ? 'true' : undefined"
          @click="selectCategory(null)"
        >
          <Compass :size="17" :stroke-width="1.75" aria-hidden="true" />
          <span>Overview</span>
        </button>
        <button
          v-for="cat in categories"
          :key="cat.name"
          type="button"
          class="sidebar-item"
          :class="{ 'sidebar-item--active': activeCategory === cat.name }"
          :aria-current="activeCategory === cat.name ? 'true' : undefined"
          @click="selectCategory(cat.name)"
        >
          <component :is="cat.icon" :size="17" :stroke-width="1.75" aria-hidden="true" />
          <span class="sidebar-item__label">{{ cat.name }}</span>
          <span class="sidebar-item__count">{{ cat.count }}</span>
        </button>
      </nav>

      <div class="content">
        <div v-if="!visible.length && !isSearching" class="intro">
          <strong>No patterns yet</strong>
          <p>The library could not be loaded. Try again in a moment.</p>
        </div>

        <p v-else-if="isSearching && !visible.length" class="status">No phrases match "{{ searchQuery }}".</p>

        <div v-else class="grid">
          <div v-for="item in visible" :key="item.id" class="item" @click="explore(item)">
            <!-- Inside a single category every card carried the same tag,
                 which told the reader nothing they had not just clicked. It
                 earns its place in Overview and in search results, where the
                 cards genuinely span categories. -->
            <span v-if="!activeCategory" class="item__tag">{{ item.category }}</span>
            <strong class="item__name">{{ item.name }}</strong>
            <div class="item__actions">
              <button
                type="button"
                class="btn"
                :class="store.isPatternSaved(item.id) ? 'btn--saved' : 'btn--outline'"
                :disabled="store.isPatternSaved(item.id)"
                @click.stop="addToCards(item)"
              >
                {{ store.isPatternSaved(item.id) ? 'Saved' : 'Add to my cards' }}
              </button>
              <button type="button" class="explore" @click.stop="explore(item)">See what this means</button>
            </div>
          </div>
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

/* Mobile-only category picker - hidden on desktop, where the sidebar does
   this job. Kept in the DOM at all sizes and toggled by media query, rather
   than v-if/v-else, so there's one source of truth for the selection. */
.category-select {
  display: none;
  width: 100%;
  padding: 11px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-strong);
  background: var(--color-frame);
  color: var(--color-text);
  font-size: 14px;
}

.layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 22px;
  align-items: start;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 5px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-bg);
  padding: 8px;
  position: sticky;
  top: 84px;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  border-radius: 8px;
  background: none;
  font-size: 13.5px;
  color: var(--color-text-muted);
  cursor: pointer;
  text-align: left;
}

.sidebar-item:hover {
  background: var(--color-surface-soft);
  color: var(--color-text);
}

.sidebar-item--active {
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
  font-weight: 600;
}

.sidebar-item__label {
  flex: 1;
  min-width: 0;
}

.sidebar-item__count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-faint);
}

.sidebar-item--active .sidebar-item__count {
  color: var(--color-primary-strong-text);
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
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

@media (max-width: 860px) {
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
  cursor: pointer;
}

.item:hover {
  border-color: var(--color-border-strong);
  background: var(--color-surface-soft);
}

/* 10.5px on --color-text-faint was 3.5:1 and under the 11px floor. */
.item__tag {
  font-family: var(--font-mono);
  font-size: 11.5px;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

.item__name {
  font-size: 15.5px;
  font-weight: 600;
  color: var(--color-text);
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

.explore {
  padding: 8px 13px;
  border-radius: 8px;
  border: 1px solid var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-primary-strong-text);
  cursor: pointer;
  white-space: nowrap;
}

.explore:hover {
  border-color: var(--color-primary-border);
}

@media (max-width: 720px) {
  .category-select {
    display: block;
  }

  .sidebar {
    display: none;
  }

  .layout {
    grid-template-columns: 1fr;
  }

  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
