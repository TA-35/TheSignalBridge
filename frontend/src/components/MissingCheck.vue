<script setup lang="ts">
// Shown under a rewrite when the draft leaves a literal reader to guess
// something - when, who, what exactly, how urgent (utils/missing.ts). Only the
// sender knows the answers, and the rewriter may not invent them, so this asks.
// An answer is used the moment it is given: a quick choice on click, typed
// words on Enter. ComposeView puts it into the draft and rewrites, and the
// card comes back with whatever is still open.
import { computed, reactive, watch } from 'vue'
import { isAnswered, type Answer, type MissingItem, type MissingKey } from '@/utils/missing'

const props = defineProps<{ items: MissingItem[] }>()
const emit = defineEmits<{ add: [answers: Partial<Record<MissingKey, Answer>>] }>()

const TITLES: Record<MissingKey, string> = {
  when: "It doesn't say when you need this",
  who: "It doesn't say who should do it",
  what: "It doesn't say exactly what you need",
  urgency: "It doesn't say how urgent this is",
}

const title = computed(() => {
  const only = props.items.length === 1 ? props.items[0]! : undefined
  return only ? (only.title ?? TITLES[only.key]) : 'Your message leaves a few things to guess'
})

// What has been typed so far, per question.
const typed = reactive<Record<string, string>>({})
watch(
  () => props.items.map((item) => `${item.key}:${item.prefill ?? ''}`).join('|'),
  () => {
    for (const key of Object.keys(typed)) delete typed[key]
    for (const item of props.items) typed[item.key] = item.prefill ?? ''
  },
  { immediate: true },
)

const typedAnswer = (item: MissingItem): Answer => ({ quick: null, typed: typed[item.key] ?? '' })

function pick(item: MissingItem, index: number) {
  emit('add', { [item.key]: { quick: index, typed: '' } })
}

function useTyped(item: MissingItem) {
  const answer = typedAnswer(item)
  if (isAnswered(item, answer)) emit('add', { [item.key]: answer })
}
</script>

<template>
  <section class="card missing" aria-labelledby="missing-title">
    <h2 id="missing-title" class="missing__title">{{ title }}</h2>
    <p class="missing__body">
      Someone who reads words literally can't fill these in, and the rewrite can't either,
      because only you know the answers. Pick or type one and your message is rewritten with it.
    </p>

    <fieldset v-for="item in items" :key="item.key" class="missing__item">
      <legend class="missing__question">{{ item.question }}</legend>

      <div v-if="item.quick.length" class="missing__quick">
        <button
          v-for="(q, i) in item.quick"
          :key="q.label"
          type="button"
          class="missing__chip"
          @click="pick(item, i)"
        >
          {{ q.label }}
        </button>
      </div>

      <!-- The draft's own sentence, to say exactly what is needed or who does it. -->
      <form v-if="item.prefill !== undefined" class="missing__typed" @submit.prevent="useTyped(item)">
        <label :for="`missing-${item.key}`" class="missing__sublabel">Your sentence</label>
        <div class="missing__row">
          <textarea
            :id="`missing-${item.key}`"
            v-model="typed[item.key]"
            rows="3"
            maxlength="400"
            @keydown.enter.exact.prevent="useTyped(item)"
          />
          <button type="submit" class="missing__use" :disabled="!isAnswered(item, typedAnswer(item))">Rewrite</button>
        </div>
        <p v-if="item.hint" class="missing__hint">{{ item.hint }}</p>
      </form>

      <form v-if="item.placeholder" class="missing__typed" @submit.prevent="useTyped(item)">
        <label :for="`missing-${item.key}`" class="missing__sublabel">
          {{ item.quick.length ? 'Or type it' : 'Type it' }}
        </label>
        <div class="missing__row">
          <input
            :id="`missing-${item.key}`"
            v-model="typed[item.key]"
            type="text"
            maxlength="120"
            :placeholder="item.placeholder"
            autocomplete="off"
          />
          <button type="submit" class="missing__use" :disabled="!isAnswered(item, typedAnswer(item))">Rewrite</button>
        </div>
      </form>
    </fieldset>

    <p class="missing__hint">
      Your answer changes your draft: a rewritten sentence replaces the old one, “Can someone”
      becomes the person you name, a time takes the place of words like “when you get a chance”,
      and softeners like “no rush” go if you need it. You can see it under “Your original”.
    </p>
  </section>
</template>

<style scoped>
.missing__title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 500;
  color: var(--color-text);
}

.missing__body {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
  max-width: 62ch;
}

.missing__item {
  display: grid;
  gap: 8px;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.missing__question {
  padding: 0;
  margin-bottom: 8px;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--color-text);
}

.missing__sublabel {
  font-size: 13px;
  color: var(--color-text-muted);
}

.missing__quick,
.missing__row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.missing__row {
  align-items: flex-start;
}

.missing__typed {
  display: grid;
  gap: 6px;
}

.missing__chip,
.missing__use {
  min-height: 40px;
  padding: 8px 16px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-frame);
  color: var(--color-text);
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.missing__chip:hover,
.missing__use:hover:not(:disabled) {
  background: var(--color-surface-soft);
}

.missing__use:disabled {
  cursor: default;
  opacity: 0.6;
}

.missing__typed textarea {
  resize: vertical;
  line-height: 1.5;
}

.missing__typed input,
.missing__typed textarea {
  flex: 1 1 220px;
  min-width: 0;
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-frame);
  color: var(--color-text);
  font: inherit;
  /* 16px or more, so phones don't zoom into the field */
  font-size: 16px;
}

.missing__hint {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-faint);
}
</style>
