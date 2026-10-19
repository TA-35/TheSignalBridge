<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Layers,
  Library,
  Mail,
  Search,
  SlidersHorizontal,
  Trash2,
} from '@lucide/vue'
import PageNav from '@/components/PageNav.vue'
import { useCardsStore } from '@/stores/cards'
import type { SavedCard } from '@/types/pattern'
import { describeOpened, savedBucket } from '@/utils/relativeTime'

const router = useRouter()
const store = useCardsStore()

// Where a card came from. `decodeId`, not `patternId`: a card saved from a
// decode that also matched the library carries both, and it is the decode
// that makes it the reader's own.
function isFromMessage(card: SavedCard): boolean {
  return card.decodeId !== null
}

// Two sources spell the same thing differently: the offline fallback patterns
// in localPatterns.ts carry their own straight quotes ('"Before the sync"'),
// the rows from /api/patterns do not. The card sets the quotation marks, so
// any the name arrives with come off first - otherwise half the list renders
// as ""Before the sync"".
function phrase(name: string): string {
  return name.replace(/^["'‘’“”]+|["'‘’“”]+$/g, '').trim() || name
}

type Source = 'all' | 'message' | 'library'
type Progress = 'any' | 'unopened' | 'opened'
type Sort = 'newest' | 'oldest' | 'opened' | 'neglect'

const source = ref<Source>('all')
const progress = ref<Progress>('any')
const sort = ref<Sort>('newest')
const query = ref('')
const page = ref(1)
const PAGE_SIZE = 6

// A card the reader has asked to delete, held one click before it goes. No
// modal: the confirmation replaces the card's own footer, so what is about to
// be deleted stays in front of them while they decide.
const pendingDelete = ref<string | null>(null)

// Phone only: the filter rail collapses behind a button, because stacked it
// pushed every card below the fold. Open state is not persisted - a reader
// who comes back is looking for their cards, not for the filters.
const filtersOpen = ref(false)

// Shown on the collapsed button so a filter that is still on cannot hide
// behind it and quietly explain a short list.
const activeFilterCount = computed(
  () => (source.value === 'all' ? 0 : 1) + (progress.value === 'any' ? 0 : 1),
)

const SORT_OPTIONS: { value: Sort; label: string }[] = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'opened', label: 'Recently opened' },
  { value: 'neglect', label: 'Least recently opened' },
]

const BUCKET_LABELS: Record<string, string> = {
  today: 'Today',
  yesterday: 'Yesterday',
  week: 'Earlier this week',
  earlier: 'Earlier',
}

const total = computed(() => store.cards.length)
const unopened = computed(() => store.cards.filter((c) => !c.lastOpened).length)

const counts = computed(() => ({
  all: total.value,
  message: store.cards.filter(isFromMessage).length,
  library: store.cards.filter((c) => !isFromMessage(c)).length,
  any: total.value,
  unopened: unopened.value,
  opened: store.cards.filter((c) => !!c.lastOpened).length,
}))

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()

  return store.cards.filter((card) => {
    if (source.value === 'message' && !isFromMessage(card)) return false
    if (source.value === 'library' && isFromMessage(card)) return false
    if (progress.value === 'unopened' && card.lastOpened) return false
    if (progress.value === 'opened' && !card.lastOpened) return false
    if (!q) return true

    return [card.name, card.category, card.excerpt, card.implies, card.meaning]
      .some((field) => field?.toLowerCase().includes(q))
  })
})

function openedTime(card: SavedCard): number {
  return card.lastOpened ? new Date(card.lastOpened).getTime() : 0
}

const sorted = computed(() => {
  const list = [...filtered.value]
  switch (sort.value) {
    case 'oldest':
      return list.sort((a, b) => a.savedAt.localeCompare(b.savedAt))
    case 'opened':
      return list.sort((a, b) => openedTime(b) - openedTime(a))
    // Never-opened cards sort first here: they are the most neglected, not
    // the least - the same rule the store's own ordering uses.
    case 'neglect':
      return list.sort(
        (a, b) => (a.lastOpened ? openedTime(a) : -Infinity) - (b.lastOpened ? openedTime(b) : -Infinity),
      )
    default:
      return list.sort((a, b) => b.savedAt.localeCompare(a.savedAt))
  }
})

const pageCount = computed(() => Math.max(1, Math.ceil(sorted.value.length / PAGE_SIZE)))
const pageItems = computed(() => sorted.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

const rangeLabel = computed(() => {
  if (!sorted.value.length) return 'No cards match these filters'
  const first = (page.value - 1) * PAGE_SIZE + 1
  const last = Math.min(page.value * PAGE_SIZE, sorted.value.length)
  return `Showing ${first} – ${last} of ${sorted.value.length} card${sorted.value.length === 1 ? '' : 's'}`
})

// Headings only while the order is "when I saved it" - under any other sort
// they would group cards that are no longer next to each other.
const grouped = computed(() => {
  if (sort.value !== 'newest' && sort.value !== 'oldest') {
    return [{ key: 'all', label: '', cards: pageItems.value }]
  }

  const buckets = new Map<string, SavedCard[]>()
  for (const card of pageItems.value) {
    const key = savedBucket(card.savedAt)
    const list = buckets.get(key)
    if (list) list.push(card)
    else buckets.set(key, [card])
  }
  return [...buckets].map(([key, cards]) => ({ key, label: BUCKET_LABELS[key] ?? '', cards }))
})

// A filter change can leave the reader on a page that no longer exists.
watch([source, progress, query, sort], () => {
  page.value = 1
})
watch(pageCount, (count) => {
  if (page.value > count) page.value = count
})

function open(id: string) {
  router.push({ name: 'card-review', params: { id } })
}

function confirmDelete(id: string) {
  store.remove(id)
  pendingDelete.value = null
}
</script>

<template>
  <div class="study">
    <div class="masthead">
      <div class="masthead__text">
        <h1>Study</h1>
        <p>
          Phrases you've saved from the library and from messages you've decoded.
        </p>
      </div>
      <div v-if="total" class="tally">
        <div class="tally__item">
          <span class="tally__num">{{ total }}</span>
          <span class="tally__label">cards saved</span>
        </div>
        <div class="tally__item">
          <span class="tally__num tally__num--open">{{ unopened }}</span>
          <span class="tally__label">not opened yet</span>
        </div>
      </div>
    </div>

    <div v-if="!total" class="empty">
      <span class="empty__mark" aria-hidden="true"><BookOpen :size="22" :stroke-width="1.6" /></span>
      <strong>No cards yet</strong>
      <p>
        Save a phrase from the Pattern library, or make a flashcard after decoding a message. Your
        cards will show up here, grouped by when you saved them.
      </p>
      <div class="empty__actions">
        <RouterLink to="/decode" class="btn btn--primary">Decode a message</RouterLink>
        <RouterLink to="/library" class="btn btn--secondary">Browse the library</RouterLink>
      </div>
    </div>

    <div v-else class="body">
      <aside class="filters" aria-label="Filter cards">
        <button
          type="button"
          class="filters__toggle"
          :class="{ 'filters__toggle--open': filtersOpen }"
          :aria-expanded="filtersOpen"
          aria-controls="study-filters"
          @click="filtersOpen = !filtersOpen"
        >
          <SlidersHorizontal :size="15" :stroke-width="1.8" aria-hidden="true" />
          Filters
          <span v-if="activeFilterCount" class="filters__badge">{{ activeFilterCount }}</span>
          <ChevronDown class="filters__caret" :size="15" :stroke-width="2" aria-hidden="true" />
        </button>

        <div id="study-filters" class="filters__panel" :class="{ 'filters__panel--open': filtersOpen }">
        <p id="filter-source" class="filters__head">Source</p>
        <div class="filters__group" role="group" aria-labelledby="filter-source">
          <button
            type="button"
            class="filter"
            :class="{ 'filter--on': source === 'all' }"
            :aria-pressed="source === 'all'"
            @click="source = 'all'"
          >
            <Layers :size="15" :stroke-width="1.8" aria-hidden="true" />
            All cards
            <span class="filter__count">{{ counts.all }}</span>
          </button>
          <button
            type="button"
            class="filter"
            :class="{ 'filter--on': source === 'message' }"
            :aria-pressed="source === 'message'"
            @click="source = 'message'"
          >
            <Mail :size="15" :stroke-width="1.8" aria-hidden="true" />
            From my messages
            <span class="filter__count">{{ counts.message }}</span>
          </button>
          <button
            type="button"
            class="filter"
            :class="{ 'filter--on': source === 'library' }"
            :aria-pressed="source === 'library'"
            @click="source = 'library'"
          >
            <Library :size="15" :stroke-width="1.8" aria-hidden="true" />
            From the library
            <span class="filter__count">{{ counts.library }}</span>
          </button>
        </div>

        <p id="filter-progress" class="filters__head">Progress</p>
        <div class="filters__group" role="group" aria-labelledby="filter-progress">
          <button
            type="button"
            class="filter"
            :class="{ 'filter--on': progress === 'any' }"
            :aria-pressed="progress === 'any'"
            @click="progress = 'any'"
          >
            Any progress
            <span class="filter__count">{{ counts.any }}</span>
          </button>
          <button
            type="button"
            class="filter"
            :class="{ 'filter--on': progress === 'unopened' }"
            :aria-pressed="progress === 'unopened'"
            @click="progress = 'unopened'"
          >
            <span class="dot dot--unopened" aria-hidden="true" />
            Not opened yet
            <span class="filter__count">{{ counts.unopened }}</span>
          </button>
          <button
            type="button"
            class="filter"
            :class="{ 'filter--on': progress === 'opened' }"
            :aria-pressed="progress === 'opened'"
            @click="progress = 'opened'"
          >
            <span class="dot dot--opened" aria-hidden="true"/>
            Opened
            <span class="filter__count">{{ counts.opened }}</span>
          </button>
        </div>
        </div>
      </aside>

      <div class="main">
        <div class="toolbar">
          <div class="search">
            <Search :size="16" :stroke-width="1.8" aria-hidden="true" />
            <input
              id="study-search"
              v-model="query"
              type="search"
              placeholder="Search your cards…"
              aria-label="Search your cards"
            />
          </div>
          <label class="sort">
            <span>Sort</span>
            <select id="study-sort" v-model="sort">
              <option v-for="opt in SORT_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
        </div>

        <p v-if="!sorted.length" class="no-match">
          No cards match these filters. Try clearing the search, or pick a different source.
        </p>

        <section v-for="group in grouped" :key="group.key" class="group">
          <h2 v-if="group.label" class="group__head">
            {{ group.label }}
            <span>{{ group.cards.length }} card{{ group.cards.length === 1 ? '' : 's' }}</span>
          </h2>

          <div class="grid">
            <article v-for="card in group.cards" :key="card.id" class="card">
              <div class="card__top">
                <span class="badge" :class="{ 'badge--message': isFromMessage(card) }">
                  <component
                    :is="isFromMessage(card) ? Mail : Library"
                    :size="13"
                    :stroke-width="1.8"
                    aria-hidden="true"
                  />
                  {{ isFromMessage(card) ? 'From your message' : 'From the library' }}
                </span>
                <button
                  type="button"
                  class="icon-btn icon-btn--danger"
                  :aria-label="`Delete card: ${phrase(card.name)}`"
                  @click="pendingDelete = card.id"
                >
                  <Trash2 :size="15" :stroke-width="1.8" aria-hidden="true" />
                </button>
              </div>
              <p class="card__name">&ldquo;{{ phrase(card.name) }}&rdquo;</p>
              <p v-if="card.excerpt" class="card__excerpt">
                In your message: &ldquo;{{ card.excerpt }}&rdquo;
              </p>

              <div v-if="pendingDelete === card.id" class="card__confirm">
                <span>Delete this card?</span>
                <div class="card__confirm-actions">
                  <button type="button" class="btn btn--danger-solid" @click="confirmDelete(card.id)">Delete</button>
                  <button type="button" class="btn btn--secondary" @click="pendingDelete = null">Keep</button>
                </div>
              </div>
              <div v-else class="card__foot">
                <span class="card__state" :class="{ 'card__state--new': !card.lastOpened }">
                  {{ describeOpened(card.lastOpened) }}
                </span>
                <button type="button" class="open-link" @click="open(card.id)">
                  See what this means
                  <ChevronRight :size="15" :stroke-width="2" aria-hidden="true" />
                </button>
              </div>
            </article>
          </div>
        </section>

        <PageNav
          v-if="sorted.length"
          v-model:page="page"
          class="pager"
          :page-count="pageCount"
          :label="rangeLabel"
        />
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

/* Baseline, not flex-start: the two sides have different type sizes, so
   matching their top edges left the numerals sitting high against "Study".
   Aligning the baselines puts the numbers on the heading's own line. */
.masthead {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
}

.masthead__text {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 60ch;
}

.masthead h1 {
  font-family: var(--font-serif);
  font-size: clamp(32px, 4.4vw, 46px);
  font-weight: 500;
  line-height: 1.08;
  letter-spacing: -0.025em;
  margin: 0;
  text-wrap: balance;
}

.masthead p {
  margin: 0;
  font-size: 15.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.tally {
  display: flex;
  margin-top: auto;
  gap: 26px;
}

.tally__item {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.tally__num {
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: bold;
  line-height: 1.1;
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

.tally__num--open {
  color: var(--color-warn-text);
}

.tally__label {
  font-size: 12.5px;
  color: var(--color-text-muted);
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
  padding: 56px 28px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}

.empty__mark {
  width: 56px;
  height: 56px;
  border-radius: 999px;
  background: var(--color-primary-soft-bg);
}

.empty strong {
  font-family: var(--font-serif);
  font-size: 24px;
  font-weight: 500;
}

.empty p {
  margin: 0;
  max-width: 44ch;
  font-size: 14.5px;
  line-height: 1.65;
  color: var(--color-text-muted);
}

.empty__actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 6px;
}

.empty__actions .btn {
  padding: 12px 20px;
  font-size: 14px;
}

/* The rail is a fixed track rather than a fraction: its labels are a known
   length, and letting it stretch on a wide screen only moves the cards away
   from the filters that drive them. */
.body {
  --rail-head: 14px;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

@media (min-width: 900px) {
  .body {
    grid-template-columns: 196px minmax(0, 1fr);
    gap: 28px;
  }

  .main {
    padding-top: calc(var(--rail-head) + 6px);
  }
}

.filters {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* Desktop keeps the rail open and has no use for the control. */
.filters__toggle {
  display: none;
}

.filters__panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filters__head {
  margin: 12px 0 0;
  height: var(--rail-head);
  line-height: var(--rail-head);
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-faint);
}

.filters__head:first-child {
  margin-top: 0;
}

.filters__group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13.5px;
  text-align: left;
  cursor: pointer;
}

.filter:hover {
  border-color: var(--color-border-strong);
}

.filter--on {
  border-color: var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
  font-weight: 600;
}

.filter__count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.filter--on .filter__count {
  color: var(--color-primary-strong-text);
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  flex: none;
}

.dot--unopened {
  background: var(--color-danger-text);
}

.dot--opened {
  background: var(--color-primary-border);
}

.main {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.search {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: 1;
  min-width: 220px;
  padding: 0 13px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-faint);
}

.search:focus-within {
  border-color: var(--color-primary);
}

.search input {
  flex: 1;
  min-width: 0;
  padding: 11px 0;
  border: none;
  background: none;
  font-size: 14px;
  color: var(--color-text);
  outline: none;
}

.search input::placeholder {
  color: var(--color-text-muted);
  opacity: 1;
}

.sort {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-muted);
}

.sort select {
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13.5px;
  font-family: inherit;
  cursor: pointer;
}

.no-match {
  margin: 0;
  padding: 28px 20px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface-soft);
  text-align: center;
  font-size: 14px;
  color: var(--color-text-muted);
}

.group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group + .group {
  margin-top: 10px;
}

.group__head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border-soft);
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 500;
  color: var(--color-text);
}

.group__head span {
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 400;
  color: var(--color-text-faint);
}

.grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
}

@media (min-width: 640px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  /* Tokens, not literals: the old ocean-blue and sage hexes ignored both the
     accent setting and dark mode, so a Lavender dark theme still showed
     sage and blue badges. */
  border: 1px solid var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
  font-size: 12px;
  font-weight: 500;
}

.badge--message {
  border-color: var(--color-warn-border);
  background: var(--color-warn-bg);
  color: var(--color-warn-text);
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
  border: none;
  border-radius: 7px;
  background: none;
  color: var(--color-text-faint);
  cursor: pointer;
}

.icon-btn:hover:not(:disabled) {
  background: var(--color-surface-soft);
  color: var(--color-text);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.icon-btn--danger:hover:not(:disabled) {
  background: var(--color-danger-bg);
  color: var(--color-danger-text);
}

.card__cat {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--color-text-muted);
}

.card__name {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--color-text);
}

.card__excerpt {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Pinned to the bottom so the footers line up across a row of cards whose
   quotes run to different lengths. */
.card__foot,
.card__confirm {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--color-border-soft);
}

.card__state {
  font-size: 12.5px;
  color: var(--color-text-muted);
}

.card__state--new {
  color: var(--color-warn-text);
}

.open-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: none;
  background: none;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary-strong-text);
  cursor: pointer;
}

.open-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.card__confirm span {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.card__confirm-actions {
  display: flex;
  gap: 8px;
}

.card__confirm .btn {
  padding: 7px 12px;
  font-size: 12.5px;
}

.pager {
  margin-top: 4px;
}

/* Phone. The rail's six full-width rows and their two headings filled the
   whole first screen, so the cards - the reason for the page - started below
   the fold. Stacked rows become wrapping chips: same filters, same counts,
   one tap each, in a fraction of the height.
   The group headings go to display:none rather than being deleted; each
   group still names itself through aria-labelledby, which reads hidden text
   just fine. */
@media (max-width: 899px) {
  .study {
    gap: 16px;
  }

  .masthead {
    gap: 10px;
  }

  .tally {
    gap: 18px;
  }

  .tally__item {
    flex-direction: row;
    align-items: baseline;
    gap: 6px;
  }

  .tally__num {
    font-size: 20px;
  }

  .filters {
    gap: 10px;
  }

  /* One row at rest. The panel below it only exists once asked for, so the
     first screen is the search box and the cards. */
  .filters__toggle {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    align-self: flex-start;
    padding: 9px 14px;
    border: 1px solid var(--color-border);
    border-radius: 999px;
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 13.5px;
    font-weight: 500;
    cursor: pointer;
  }

  .filters__toggle--open {
    border-color: var(--color-primary-soft-border);
    background: var(--color-primary-soft-bg);
    color: var(--color-primary-strong-text);
  }

  /* The count of filters currently narrowing the list - without it, a reader
     who left "From the library" on sees a short list and no reason for it. */
  .filters__badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    border-radius: 999px;
    background: var(--color-primary);
    color: var(--color-frame);
    font-size: 11px;
    font-weight: 600;
  }

  .filters__caret {
    transition: transform 160ms ease;
  }

  @media (prefers-reduced-motion: reduce) {
    .filters__caret {
      transition: none;
    }
  }

  .filters__toggle--open .filters__caret {
    transform: rotate(180deg);
  }

  .filters__panel {
    display: none;
  }

  .filters__panel--open {
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    gap: 8px;
  }

  .filters__head {
    display: none;
  }

  .filters__group {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 8px;
    width: 100%;
  }

  .filter {
    width: auto;
    padding: 7px 12px;
    border-radius: 999px;
    font-size: 13px;
  }

  .filter__count {
    margin-left: 2px;
  }

  .body,
  .main {
    gap: 14px;
  }

  .nudge {
    flex-wrap: wrap;
  }

  .nudge p {
    min-width: 60%;
  }
}

</style>
