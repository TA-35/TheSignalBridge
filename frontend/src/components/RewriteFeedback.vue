<script setup lang="ts">
// 👍/👎 on what Compose gave back. Sent: the vote, reasons ticked from a fixed
// list, the model's name and two yes/no facts about how the answer was
// reached. Never the draft or the rewrite - the privacy page promises those
// are never stored, and the API refuses any field that could carry them.
// The totals per model show what the next training run has to fix.
import { ref } from 'vue'
import { FEEDBACK_REASONS, sendComposeFeedback } from '@/services/composeService'
import type { FeedbackReason } from '@/types/compose'

const props = defineProps<{
  model: string
  /** The model said the draft was already clear and kept it as written. */
  keptAsWritten: boolean
  /** The sender answered the "what's missing" questions to get this answer. */
  afterCard: boolean
}>()

const step = ref<'ask' | 'why' | 'sending' | 'thanks' | 'failed'>('ask')
const vote = ref<'up' | 'down'>('up')
const picked = ref<FeedbackReason[]>([])
const sent = ref<FeedbackReason[]>([])

async function send(reasons: FeedbackReason[]) {
  sent.value = reasons
  step.value = 'sending'
  const saved = await sendComposeFeedback({
    vote: vote.value,
    reasons,
    model: props.model,
    kept_as_written: props.keptAsWritten,
    after_card: props.afterCard,
  })
  step.value = saved ? 'thanks' : 'failed'
}

function rate(choice: 'up' | 'down') {
  vote.value = choice
  if (choice === 'up') void send([])
  // "Already clear" can only be wrong one way: it needed a rewrite.
  else if (props.keptAsWritten) void send(['needed_rewrite'])
  else step.value = 'why'
}

function toggle(code: FeedbackReason) {
  picked.value = picked.value.includes(code) ? picked.value.filter((c) => c !== code) : [...picked.value, code]
}
</script>

<template>
  <section class="card feedback" aria-labelledby="feedback-title">
    <h2 id="feedback-title" class="feedback__title">
      {{ keptAsWritten ? 'Was it right to leave your message as it was?' : 'Was this rewrite helpful?' }}
    </h2>

    <div v-if="step === 'ask'" class="feedback__row">
      <button type="button" class="feedback__btn" @click="rate('up')">
        <span aria-hidden="true">👍</span> Yes
      </button>
      <button type="button" class="feedback__btn" @click="rate('down')">
        <span aria-hidden="true">👎</span> No
      </button>
    </div>

    <form v-else-if="step === 'why'" class="feedback__why" @submit.prevent="send(picked)">
      <p class="feedback__question">What was wrong with it? Pick any that apply.</p>
      <div class="feedback__row">
        <button
          v-for="reason in FEEDBACK_REASONS"
          :key="reason.code"
          type="button"
          class="feedback__chip"
          :aria-pressed="picked.includes(reason.code)"
          @click="toggle(reason.code)"
        >
          {{ reason.label }}
        </button>
      </div>
      <div class="feedback__row">
        <button type="submit" class="feedback__btn">Send</button>
        <button type="button" class="feedback__link" @click="send([])">Skip</button>
      </div>
    </form>

    <p v-else class="feedback__done" role="status">
      <template v-if="step === 'sending'">Sending…</template>
      <template v-else-if="step === 'thanks'">Thanks. Ratings like this decide what the rewriter learns next.</template>
      <template v-else>
        That didn't send.
        <button type="button" class="feedback__link" @click="send(sent)">Try again</button>
      </template>
    </p>

    <p class="feedback__privacy">Only your rating is saved, never your message or the rewrite.</p>
  </section>
</template>

<style scoped>
.feedback__title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 500;
  color: var(--color-text);
}

.feedback__row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.feedback__why {
  display: grid;
  gap: 10px;
}

.feedback__question,
.feedback__done {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--color-text);
}

.feedback__btn,
.feedback__chip {
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

.feedback__btn:hover,
.feedback__chip:hover {
  background: var(--color-surface-soft);
}

.feedback__chip[aria-pressed='true'] {
  border-color: var(--color-text);
  background: var(--color-surface-soft);
  box-shadow: inset 0 0 0 1px var(--color-text);
}

.feedback__link {
  min-height: 40px;
  padding: 8px 4px;
  border: 0;
  background: none;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 14px;
  text-decoration: underline;
  cursor: pointer;
}

.feedback__privacy {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-faint);
}
</style>
