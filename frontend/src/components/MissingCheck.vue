<script setup lang="ts">
// Shown under a rewrite when the draft leaves a literal reader to guess
// something - when, who, what exactly, how urgent (utils/missing.ts). Only the
// sender knows the answers, and the rewriter may not invent them, so this asks.
// ComposeView adds the answers to the draft and rewrites once.
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

const title = computed(() =>
  props.items.length === 1 ? TITLES[props.items[0]!.key] : 'Your message leaves a few things to guess',
)

// One answer per question: a quick choice or typed words, whichever came last.
const answers = reactive<Record<string, Answer>>({})
watch(
  () => props.items.map((item) => item.key).join(),
  () => {
    for (const key of Object.keys(answers)) delete answers[key]
    for (const item of props.items) answers[item.key] = { quick: null, typed: item.prefill ?? '' }
  },
  { immediate: true },
)

function pick(key: MissingKey, index: number) {
  const answer = answers[key]!
  answer.quick = answer.quick === index ? null : index
  answer.typed = ''
}

function typed(key: MissingKey) {
  answers[key]!.quick = null
}

// The questions the sender has actually answered.
const given = computed(() => {
  const out: Partial<Record<MissingKey, Answer>> = {}
  for (const item of props.items) {
    const answer = answers[item.key]
    if (answer && isAnswered(item, answer)) out[item.key] = { ...answer }
  }
  return out
})
const hasAnswer = computed(() => Object.keys(given.value).length > 0)

function submit() {
  if (hasAnswer.value) emit('add', given.value)
}
</script>

<template>
  <section class="card missing" aria-labelledby="missing-title">
    <h2 id="missing-title" class="missing__title">{{ title }}</h2>
    <p class="missing__body">
      Someone who reads words literally can't fill these in, and the rewrite can't either,
      because only you know the answers. Answer any of them and your message is rewritten with them.
    </p>

    <form class="missing__form" @submit.prevent="submit">
      <fieldset v-for="item in items" :key="item.key" class="missing__item">
        <legend class="missing__question">{{ item.question }}</legend>

        <div v-if="item.quick.length" class="missing__quick">
          <button
            v-for="(q, i) in item.quick"
            :key="q.label"
            type="button"
            class="missing__chip"
            :class="{ 'missing__chip--on': answers[item.key]?.quick === i }"
            :aria-pressed="answers[item.key]?.quick === i"
            @click="pick(item.key, i)"
          >
            {{ q.label }}
          </button>
        </div>

        <div v-if="item.prefill !== undefined && answers[item.key]" class="missing__typed">
          <label :for="`missing-${item.key}`" class="missing__sublabel">Your sentence</label>
          <textarea
            :id="`missing-${item.key}`"
            v-model="answers[item.key]!.typed"
            rows="3"
            maxlength="400"
          />
          <p class="missing__hint">
            Say what should be done and to what, such as “Could you fix the totals in the numbers
            section so they match the finance report?”
          </p>
        </div>

        <div v-if="item.placeholder && answers[item.key]" class="missing__typed">
          <label :for="`missing-${item.key}`" class="missing__sublabel">
            {{ item.quick.length ? 'Or type it' : 'Type it' }}
          </label>
          <input
            :id="`missing-${item.key}`"
            v-model="answers[item.key]!.typed"
            type="text"
            maxlength="120"
            :placeholder="item.placeholder"
            autocomplete="off"
            @input="typed(item.key)"
          />
        </div>
      </fieldset>

      <div class="missing__actions">
        <button type="submit" class="missing__add" :disabled="!hasAnswer">Add to my message and rewrite</button>
        <p class="missing__hint">
          Your answers change your draft: your rewritten sentence replaces the old one, softeners like
          “no rush” go if it's urgent, and a deadline is added, such as “I need this by 3pm Friday.”
          You can see it under “Your original”.
        </p>
      </div>
    </form>
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

.missing__form {
  display: grid;
  gap: 18px;
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

.missing__quick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.missing__typed {
  display: grid;
  gap: 6px;
}

.missing__chip,
.missing__add {
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
.missing__add:hover:not(:disabled) {
  background: var(--color-surface-soft);
}

/* A mark as well as a fill: selected has to survive greyscale. */
.missing__chip--on,
.missing__chip--on:hover {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

.missing__chip--on::before {
  content: '✓ ';
}

.missing__add {
  justify-self: start;
}

.missing__add:disabled {
  cursor: default;
  opacity: 0.6;
}

.missing__typed textarea {
  resize: vertical;
  line-height: 1.5;
}

.missing__typed input,
.missing__typed textarea {
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

.missing__actions {
  display: grid;
  gap: 8px;
}

.missing__hint {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-faint);
}
</style>
