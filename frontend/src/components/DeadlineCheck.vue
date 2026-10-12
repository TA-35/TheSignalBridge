<script setup lang="ts">
// Shown under a rewrite when the model found an ask but no deadline. Only the
// sender knows the deadline, and the rewriter may not invent one, so this asks
// them for it. ComposeView adds their choice to the draft and rewrites again.
import { ref } from 'vue'
import { deadlineSentence, QUICK_DEADLINES } from '@/utils/deadline'

const emit = defineEmits<{ add: [sentence: string] }>()

const typed = ref('')
function addTyped() {
  const sentence = deadlineSentence(typed.value)
  if (sentence) emit('add', sentence)
}
</script>

<template>
  <section class="card deadline" aria-labelledby="deadline-title">
    <h2 id="deadline-title" class="deadline__title">It doesn't say when you need this</h2>
    <p class="deadline__body">
      Someone who reads words literally can't guess a deadline, and the rewrite can't add one,
      because only you know it. Pick one and the message is rewritten with it.
    </p>

    <p id="deadline-question" class="deadline__label">When do you need it?</p>
    <div class="deadline__quick" role="group" aria-labelledby="deadline-question">
      <button
        v-for="q in QUICK_DEADLINES"
        :key="q.label"
        type="button"
        class="deadline__chip"
        @click="emit('add', q.sentence)"
      >
        {{ q.label }}
      </button>
    </div>

    <form class="deadline__own" @submit.prevent="addTyped">
      <label for="deadline-typed" class="deadline__label">Or type it</label>
      <div class="deadline__row">
        <input id="deadline-typed" v-model="typed" type="text" maxlength="60" placeholder="3pm Friday" autocomplete="off" />
        <button type="submit" class="deadline__add" :disabled="!typed.trim()">Add and rewrite</button>
      </div>
    </form>

    <p class="deadline__hint">It goes into your draft as one sentence, such as “I need this by 3pm Friday.”</p>
  </section>
</template>

<style scoped>
.deadline__title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 500;
  color: var(--color-text);
}

.deadline__body {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
  max-width: 62ch;
}

.deadline__label {
  margin: 4px 0 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-text);
}

.deadline__quick,
.deadline__row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.deadline__own {
  display: grid;
  gap: 8px;
}

.deadline__chip,
.deadline__add {
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

.deadline__chip:hover,
.deadline__add:hover:not(:disabled) {
  background: var(--color-surface-soft);
}

.deadline__add:disabled {
  cursor: default;
  opacity: 0.6;
}

.deadline__row input {
  flex: 1 1 180px;
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

.deadline__hint {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-faint);
}
</style>
