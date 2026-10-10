<script setup lang="ts">
// A small line drawing for each pattern category, so a card can be told apart
// by shape as well as by colour. Drawn in currentColor: the card sets the colour.
//
//   Softened request  - a speech bubble with a wavy line: the ask is cushioned
//   Vague deadline    - a clock with a dotted rim: a time, just not a stated one
//   Unassigned owner  - a task handed towards a dotted person: nobody is named
//   Unclear priority  - three equal tasks, an arrow both ways: which comes first?
//   Undefined scope   - a box with dotted edges: work, but not where it ends
//   Feedback framing  - a bubble with layered lines: the point sits between kind words
defineProps<{ category: string; size?: number }>()
</script>

<template>
  <svg
    :width="size ?? 56"
    :height="size ?? 56"
    viewBox="0 0 48 48"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-if="category === 'Softened request'">
      <path d="M8 12c0-2.2 1.8-4 4-4h24c2.2 0 4 1.8 4 4v16c0 2.2-1.8 4-4 4H20l-8 7v-7c-2.2 0-4-1.8-4-4z" />
      <path d="M15 20c2-2.5 4-2.5 6 0s4 2.5 6 0 4-2.5 6 0" />
    </template>
    <template v-else-if="category === 'Vague deadline'">
      <circle cx="24" cy="25" r="15" stroke-dasharray="3 4" />
      <path d="M24 25V16" />
      <path d="M24 25l6 4" stroke-dasharray="2 3" />
      <path d="M19 6h10" />
    </template>
    <template v-else-if="category === 'Unassigned owner'">
      <rect x="6" y="20" width="14" height="12" rx="2" />
      <path d="M6 24h14" />
      <path d="M23 26h8m-3-3 3 3-3 3" />
      <circle cx="38" cy="18" r="4" stroke-dasharray="2.5 3" />
      <path d="M31 36c0-4 3-7 7-7s7 3 7 7" stroke-dasharray="2.5 3" />
    </template>
    <template v-else-if="category === 'Unclear priority'">
      <rect x="7" y="10" width="22" height="7" rx="2" />
      <rect x="7" y="21" width="22" height="7" rx="2" />
      <rect x="7" y="32" width="22" height="7" rx="2" />
      <path d="M36 12v24m-4-20 4-4 4 4m-8 16 4 4 4-4" />
    </template>
    <template v-else-if="category === 'Undefined scope'">
      <path d="M10 10h12M10 10v12" />
      <path d="M38 38H26m12 0V26" />
      <rect x="10" y="10" width="28" height="28" rx="3" stroke-dasharray="3 4" />
      <path d="M19 24h10m-5-5v10" />
    </template>
    <template v-else-if="category === 'Feedback framing'">
      <path d="M8 12c0-2.2 1.8-4 4-4h24c2.2 0 4 1.8 4 4v16c0 2.2-1.8 4-4 4H20l-8 7v-7c-2.2 0-4-1.8-4-4z" />
      <path d="M15 15h18M15 20h12M15 25h18" />
      <path d="M38 4v4m-2-2h4" />
    </template>
    <template v-else>
      <!-- a category the library doesn't know yet: a plain card shape -->
      <rect x="9" y="11" width="30" height="26" rx="3" />
      <path d="M15 20h18M15 27h12" />
    </template>
  </svg>
</template>
