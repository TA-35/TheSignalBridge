<script setup lang="ts">
// The pager shared by Study and Library. It lived in both views, which meant
// two copies of the same markup and the same CSS drifting apart - they had
// already drifted once.
//
// The page numbers collapse once there are more than seven pages: first,
// last, the current page and its neighbours, with a gap where numbers were
// dropped. Without that, a reader with 200 saved cards gets a row of 34
// buttons under six cards.
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from '@lucide/vue'

const props = defineProps<{
  page: number
  pageCount: number
  /** The count line on the left, e.g. "Showing 1–6 of 17 cards". */
  label?: string
}>()

const emit = defineEmits<{ 'update:page': [value: number] }>()

// Below this every page gets its own button; above it, numbers collapse.
// Seven is the widest run that still fits beside the count line on a phone.
const MAX_SHOWN = 7

type Slot = { kind: 'page'; n: number } | { kind: 'gap'; key: string }

const slots = computed<Slot[]>(() => {
  const total = props.pageCount
  if (total <= MAX_SHOWN) {
    return Array.from({ length: total }, (_, i) => ({ kind: 'page', n: i + 1 }))
  }

  // Always the ends and the current page's immediate neighbours, so the
  // reader can always step one page or jump to either end.
  const wanted = new Set([1, total, props.page - 1, props.page, props.page + 1])
  const shown = [...wanted].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b)

  const out: Slot[] = []
  let previous = 0
  for (const n of shown) {
    // A gap standing in for exactly one page would be wider than the page
    // it hides, so render the number instead.
    if (n - previous === 2) out.push({ kind: 'page', n: n - 1 })
    else if (n - previous > 2) out.push({ kind: 'gap', key: `gap-${previous}-${n}` })
    out.push({ kind: 'page', n })
    previous = n
  }
  return out
})

function go(n: number) {
  if (n >= 1 && n <= props.pageCount && n !== props.page) emit('update:page', n)
}
</script>

<template>
  <div class="pager">
    <span class="pager__range">{{ label }}</span>

    <nav v-if="pageCount > 1" class="pager__nav" aria-label="Pagination">
      <button type="button" class="icon-btn" :disabled="page === 1" aria-label="Previous page" @click="go(page - 1)">
        <ChevronLeft :size="16" :stroke-width="2" aria-hidden="true" />
      </button>

      <template v-for="slot in slots" :key="slot.kind === 'page' ? slot.n : slot.key">
        <button
          v-if="slot.kind === 'page'"
          type="button"
          class="pager__page"
          :class="{ 'pager__page--on': slot.n === page }"
          :aria-current="slot.n === page ? 'page' : undefined"
          @click="go(slot.n)"
        >
          {{ slot.n }}
        </button>
        <!-- Not a button: there is no single page it would take you to. -->
        <span v-else class="pager__gap" aria-hidden="true">…</span>
      </template>

      <button
        type="button"
        class="icon-btn"
        :disabled="page === pageCount"
        aria-label="Next page"
        @click="go(page + 1)"
      >
        <ChevronRight :size="16" :stroke-width="2" aria-hidden="true" />
      </button>
    </nav>
  </div>
</template>

<style scoped>
.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding-top: 14px;
  border-top: 1px solid var(--color-border-soft);
}

.pager__range {
  font-size: 13px;
  color: var(--color-text-muted);
}

.pager__nav {
  display: flex;
  align-items: center;
  gap: 4px;
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

.pager__page {
  min-width: 34px;
  padding: 7px 10px;
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-text);
  font-family: inherit;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}

.pager__page:hover:not(.pager__page--on) {
  border-color: var(--color-border-strong);
}

.pager__page--on {
  border-color: var(--color-primary-border);
  background: var(--color-primary);
  color: var(--color-frame);
  font-weight: 600;
}

.pager__gap {
  padding: 0 2px;
  color: var(--color-text-faint);
  font-size: 13px;
}
</style>
