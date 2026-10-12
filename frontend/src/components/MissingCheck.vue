<script setup lang="ts">
// Shown under a rewrite when the draft leaves a literal reader to guess
// something - when, who, what exactly, how urgent (utils/missing.ts). Only the
// sender knows the answers, and the rewriter may not invent them, so this asks.
// An answer is used the moment it is given: a quick choice on click, typed
// words on Enter or "Update message". ComposeView puts it into the draft and
// rewrites in place (`busy` while it does), and the card comes back with
// whatever is still open, or says that's everything.
//
// Laid out to be read at a glance: a count in the title, then for each
// question a numbered name, one short question, and the sender's own words that
// raised it, highlighted. How it works is one line under the title, not a
// paragraph at the top and another at the bottom.
import { computed, reactive, watch } from 'vue'
import { Check } from '@lucide/vue'
import { isAnswered, type Answer, type MissingItem, type MissingKey } from '@/utils/missing'

const props = defineProps<{ items: MissingItem[]; busy?: boolean }>()
const emit = defineEmits<{ add: [answers: Partial<Record<MissingKey, Answer>>] }>()

const COUNTS = ['One quick question', 'Two quick questions', 'Three quick questions', 'Four quick questions']
const heading = computed(() => {
  if (props.items.length) return COUNTS[props.items.length - 1] ?? 'A few quick questions'
  return props.busy ? 'Adding your answer' : "That's everything"
})

const LABELS: Record<MissingKey, string> = { when: 'When', who: 'Who', what: 'What exactly', urgency: 'How urgent' }
// What a typed answer is, for its label: "Or type a name".
const TYPED: Partial<Record<MissingKey, string>> = { when: 'a day or time', who: 'a name' }

// What has been typed so far per question, and which were sent before they said anything.
const typed = reactive<Record<string, string>>({})
const nudged = reactive<Record<string, boolean>>({})
watch(
  () => props.items.map((item) => `${item.key}:${item.prefill ?? ''}`).join('|'),
  () => {
    for (const key of Object.keys(typed)) delete typed[key]
    for (const key of Object.keys(nudged)) delete nudged[key]
    for (const item of props.items) typed[item.key] = item.prefill ?? ''
  },
  { immediate: true },
)

const typedAnswer = (item: MissingItem): Answer => ({ quick: null, typed: typed[item.key] ?? '' })

function pick(item: MissingItem, index: number) {
  emit('add', { [item.key]: { quick: index, typed: '' } })
}

// The button is never greyed out: pressed before the answer says anything, it
// says what's needed rather than silently doing nothing.
function useTyped(item: MissingItem) {
  const answer = typedAnswer(item)
  if (isAnswered(item, answer)) emit('add', { [item.key]: answer })
  else nudged[item.key] = true
}

function nudge(item: MissingItem): string {
  if (item.prefill === undefined) {
    return item.key === 'when' ? 'Type a day or time first, such as 3pm Friday.' : 'Type a name first.'
  }
  return item.prefill
    ? 'Change the sentence first, then press Update message.'
    : 'Write a full sentence first, then press Update message.'
}
</script>

<template>
  <section class="card missing" aria-labelledby="missing-title">
    <header>
      <h2 id="missing-title" class="missing__title">
        <span v-if="!items.length && !busy" class="missing__done" aria-hidden="true">
          <Check :size="15" :stroke-width="2.4" />
        </span>
        {{ heading }}
      </h2>
      <p v-if="items.length" class="missing__lede">
        Only you know the answers. Each one updates your message straight away.
      </p>
      <p v-else-if="!busy" class="missing__lede">
        Your answers are in the message above. Copy it when you're ready.
      </p>
      <!-- Always in the page, so a screen reader hears it change. -->
      <p class="missing__status" role="status">{{ busy ? 'Updating your message…' : '' }}</p>
    </header>

    <div
      v-for="(item, i) in items"
      :key="item.key"
      class="missing__item"
      role="group"
      :aria-labelledby="`missing-q-${item.key}`"
    >
      <p class="missing__kind">
        <span class="missing__num" aria-hidden="true">{{ i + 1 }}</span>
        {{ item.label ?? LABELS[item.key] }}
      </p>
      <h3 :id="`missing-q-${item.key}`" class="missing__question">{{ item.question }}</h3>
      <p v-if="item.why" class="missing__why">
        <template v-if="item.quote">You wrote <mark class="missing__quote">“{{ item.quote }}”</mark>. </template>
        {{ item.why }}
      </p>

      <div v-if="item.quick.length" class="missing__choices">
        <button
          v-for="(q, qi) in item.quick"
          :key="q.label"
          type="button"
          class="missing__choice"
          :disabled="busy"
          @click="pick(item, qi)"
        >
          {{ q.label }}
        </button>
      </div>

      <!-- The draft's own sentence, to say exactly what is needed or who does it. -->
      <form v-if="item.prefill !== undefined" class="missing__typed" @submit.prevent="useTyped(item)">
        <label :for="`missing-${item.key}`" class="missing__label">{{ item.fieldLabel ?? 'Your sentence' }}</label>
        <textarea
          :id="`missing-${item.key}`"
          v-model="typed[item.key]"
          rows="3"
          maxlength="400"
          :disabled="busy"
          :aria-describedby="item.example ? `missing-ex-${item.key}` : undefined"
          @input="nudged[item.key] = false"
          @keydown.enter.exact.prevent="useTyped(item)"
        />
        <p v-if="item.example" :id="`missing-ex-${item.key}`" class="missing__example">
          For example: “{{ item.example }}”
        </p>
        <div class="missing__actions">
          <button type="submit" class="missing__update" :disabled="busy">Update message</button>
          <span class="missing__enter">or press Enter</span>
        </div>
        <p class="missing__nudge" role="status">{{ nudged[item.key] ? nudge(item) : '' }}</p>
      </form>

      <form v-if="item.placeholder" class="missing__typed" @submit.prevent="useTyped(item)">
        <label :for="`missing-${item.key}`" class="missing__label">
          {{ item.quick.length ? 'Or type' : 'Type' }} {{ TYPED[item.key] ?? 'it' }}
        </label>
        <input
          :id="`missing-${item.key}`"
          v-model="typed[item.key]"
          type="text"
          maxlength="120"
          :placeholder="item.placeholder"
          autocomplete="off"
          :disabled="busy"
          @input="nudged[item.key] = false"
        />
        <div class="missing__actions">
          <button type="submit" class="missing__update" :disabled="busy">Update message</button>
          <span class="missing__enter">or press Enter</span>
        </div>
        <p class="missing__nudge" role="status">{{ nudged[item.key] ? nudge(item) : '' }}</p>
      </form>
    </div>
  </section>
</template>

<style scoped>
/* More specific than ComposeView's .card, which also lands on this root. */
.card.missing {
  /* Control borders at 3:1 or more on the card in every theme: the same mix
     the redesign branch calls --color-border-muted. --color-border-strong is
     about 1.6:1 here, too faint to show where a button or a box is. */
  --missing-control: color-mix(in srgb, var(--color-text-muted) 85%, var(--color-surface));
  gap: 22px;
  padding: 26px;
  border-color: var(--color-primary-soft-border);
}

.missing__title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-family: var(--font-serif);
  font-size: 21px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--color-text);
}

.missing__done {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

.missing__lede {
  max-width: 62ch;
  margin: 6px 0 0;
  font-size: 15px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.missing__status {
  margin: 0;
  font-size: 15px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.missing__status:not(:empty) {
  margin-top: 10px;
}

.missing__item {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.missing__item + .missing__item {
  padding-top: 22px;
  border-top: 1px solid var(--color-border-soft);
}

.missing__kind {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-primary-strong-text);
}

.missing__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: var(--color-primary-soft-bg);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.missing__question {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--color-text);
}

.missing__why {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.missing__quote {
  padding: 1px 6px;
  border-radius: 5px;
  background: var(--color-warn-bg);
  box-shadow: inset 0 0 0 1px var(--color-warn-border);
  color: var(--color-warn-text);
  font-weight: 500;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
}

.missing__choices {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 4px;
}

.missing__choice,
.missing__update {
  min-height: 44px;
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}

.missing__choice {
  padding: 10px 18px;
  border: 1px solid var(--missing-control);
  background: var(--color-frame);
  color: var(--color-text);
  text-align: left;
}

.missing__choice:hover:not(:disabled) {
  border-color: var(--color-text);
  background: var(--color-surface-soft);
}

.missing__update {
  padding: 10px 20px;
  border: 1px solid var(--color-primary-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

.missing__update:hover:not(:disabled) {
  background: var(--color-primary-soft-border);
}

.missing__choice:disabled,
.missing__update:disabled {
  cursor: default;
  opacity: 0.6;
}

/* Spaced by margins, so an empty nudge takes no room. */
.missing__typed {
  display: flex;
  flex-direction: column;
  margin-top: 4px;
}

.missing__typed > * {
  margin: 0;
}

.missing__typed > * + * {
  margin-top: 8px;
}

.missing__typed > .missing__actions {
  margin-top: 12px;
}

.missing__typed > .missing__nudge:empty {
  margin-top: 0;
}

.missing__label {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.missing__typed input,
.missing__typed textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 44px;
  padding: 10px 14px;
  border: 1px solid var(--missing-control);
  border-radius: var(--radius-sm);
  background: var(--color-frame);
  color: var(--color-text);
  font: inherit;
  /* 16px or more, so phones don't zoom into the field */
  font-size: 16px;
  line-height: 1.5;
}

.missing__typed textarea {
  min-height: 96px;
  resize: vertical;
}

.missing__example {
  font-size: 14px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.missing__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.missing__enter {
  font-size: 13.5px;
  color: var(--color-text-faint);
}

.missing__nudge {
  font-size: 14px;
  line-height: 1.5;
  color: var(--color-warn-text);
}

@media (max-width: 640px) {
  .card.missing {
    padding: 20px;
  }

  .missing__choices {
    flex-direction: column;
  }

  .missing__choice,
  .missing__update {
    width: 100%;
    min-height: 48px;
  }

  /* On a phone the full-width button is the way to send. */
  .missing__enter {
    display: none;
  }
}
</style>
