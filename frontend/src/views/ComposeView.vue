<script setup lang="ts">
// The other direction from Decode. You paste a message you have already
// written; it comes back saying the same thing more explicitly, with a short
// account of what changed.
//
// What this page deliberately does NOT do: pick a tone. The rewrite keeps
// the register of the draft - the classifiers tell the model what that
// register is, and the eval penalises a rewrite whose politeness drops. A
// tone selector here would promise something the model is not trained to do.
import { computed, reactive, ref } from 'vue'
import { Check, Copy, Lightbulb } from '@lucide/vue'
import {
  composeMessage,
  EmptyMessageError,
  MAX_MESSAGE_LENGTH,
  MessageTooLongError,
} from '@/services/composeService'
import { isAlreadyClear, type ComposeQuick, type ComposeResult } from '@/types/compose'

const SAMPLE =
  "Hi,\n\nWhen you get a chance, could you take a look at the Q3 deck and tighten up the numbers section? Would be great to have it before the leadership sync.\n\nThanks!"

const state = reactive({
  message: '',
  error: '',
  errorTitle: '',
  loading: false,
  quick: null as ComposeQuick | null,
  result: null as ComposeResult | null,
})

// Advisory wording for the three classifiers, matching how the decode page
// says the same thing - these are a guess from the wording, not a fact about
// the writer.
const REGISTER_WORDS: Record<string, Record<string, string>> = {
  politeness: { high: 'politely worded', medium: 'plainly worded', low: 'blunt' },
  tone: { formal: 'formal', neutral: 'neutral in tone', casual: 'casual' },
  circa: { direct: 'a direct ask', indirect: 'an indirect ask' },
}
const LOW_CONFIDENCE = 0.4

const signals = computed(() => state.result?.signals ?? state.quick?.signals ?? [])

const registerChips = computed(() =>
  signals.value
    .map((s) => ({
      model: s.model,
      word: REGISTER_WORDS[s.model]?.[s.label] ?? '',
      unsure: s.confidence < LOW_CONFIDENCE,
    }))
    .filter((c) => c.word),
)

const alreadyClear = computed(() => !!state.result && isAlreadyClear(state.result))

/** The five fields the model reports, in a fixed order, empty ones dropped. */
const meaningRows = computed(() => {
  const meaning = state.result?.meaning
  if (!meaning) return []
  return [
    { label: 'The ask', value: meaning.ask },
    { label: 'By when', value: meaning.deadline },
    { label: 'How urgent', value: meaning.urgency },
    { label: 'Reads as', value: meaning.tone },
    { label: 'Left unsaid', value: meaning.implied },
  ].filter((row) => !!row.value)
})

async function rewrite() {
  const text = state.message.trim()
  state.error = ''
  state.errorTitle = ''
  state.quick = null
  state.result = null
  state.loading = true

  try {
    state.result = await composeMessage(text, (quick) => {
      state.quick = quick
    })
  } catch (err) {
    if (err instanceof EmptyMessageError) {
      state.errorTitle = 'Nothing to rewrite yet'
      state.error = 'Paste the message you are about to send and we will go through it.'
    } else if (err instanceof MessageTooLongError) {
      state.errorTitle = 'That message is too long'
      state.error = err.message
    } else {
      state.errorTitle = 'Something went wrong'
      state.error = 'Try again in a moment.'
    }
  } finally {
    state.loading = false
  }
}

function loadSample() {
  state.message = SAMPLE
  state.error = ''
}

function startOver() {
  state.message = ''
  state.result = null
  state.quick = null
  state.error = ''
  state.errorTitle = ''
}

function editDraft() {
  state.result = null
  state.quick = null
}

const copyState = ref<'idle' | 'copied' | 'failed'>('idle')
let copyResetTimer: ReturnType<typeof setTimeout> | undefined

async function copyRewrite() {
  const text = state.result?.rewrite
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copyState.value = 'copied'
  } catch {
    copyState.value = 'failed'
  }
  clearTimeout(copyResetTimer)
  copyResetTimer = setTimeout(() => {
    copyState.value = 'idle'
  }, 2000)
}
</script>

<template>
  <div class="compose">
    <!-- Intake ------------------------------------------------------- -->
    <template v-if="!state.result">
      <div class="intro">
        <h1>Make your message clear</h1>
        <p>
          Paste a message you're about to send. 
          We'll make it clear so it can't be misread.
        </p>
      </div>

      <div class="panes">
        <div class="pane">
          <div class="pane__head">
            <span class="pane__label">Your draft</span>
            <span
              class="char-count"
              :class="{ 'char-count--over': state.message.length > MAX_MESSAGE_LENGTH }"
            >
              {{ state.message.length }} / {{ MAX_MESSAGE_LENGTH }}
            </span>
          </div>

          <textarea
            id="compose-draft"
            v-model="state.message"
            class="draft-box"
            :class="{ 'draft-box--error': !!state.error }"
            placeholder="Hi, when you get a chance, could you take a look at…"
            spellcheck="false"
            :aria-invalid="!!state.error"
            :aria-describedby="state.error ? 'compose-error' : undefined"
          />

          <div v-if="state.error" id="compose-error" class="error-banner" role="alert">
            <span class="error-dot" />
            <div>
              <strong>{{ state.errorTitle }}</strong>
              <p>{{ state.error }}</p>
            </div>
          </div>

          <div class="pane__foot">
            <button type="button" class="link-button" @click="loadSample">Use a sample message</button>
            <div class="pane__buttons">
              <button type="button" class="btn btn--secondary" @click="startOver">Clear</button>
              <button type="button" class="btn btn--primary" :disabled="state.loading" @click="rewrite">
                {{ state.loading ? 'Rewriting...' : 'Compose' }}
              </button>
            </div>
          </div>
        </div>

        <aside class="pane pane--preview">
          <span class="preview__mark" aria-hidden="true">
            <Lightbulb :size="22" :stroke-width="1.6" />
          </span>
          <h2 class="preview__title">What comes back</h2>
          <p class="preview__note">
            1. We find hints, hedges and hidden deadlines in your message.
          </p>
          <p class="preview__note">
            2. We rewrite it so the ask and the timing are stated plainly.
          </p>
          <p class="preview__note">
            3. You see what changed and why, then copy it or keep your original.
          </p>
        </aside>
      </div>
    </template>

    <!-- Result ------------------------------------------------------- -->
    <template v-else>
      <div class="results-header">
        <div>
          <h1>{{ alreadyClear ? 'This one already reads clearly' : "Here's a clearer version" }}</h1>
          <p>Nothing is sent from here. Copy it when you are ready.</p>
        </div>
        <button type="button" class="btn btn--ghost" @click="editDraft">Edit draft</button>
      </div>

      <p v-if="registerChips.length" class="register">
        <span class="register__lead">Your draft reads as</span>
        <span v-for="chip in registerChips" :key="chip.model" class="register__chip">
          {{ chip.word }}<template v-if="chip.unsure"> (not sure)</template>
        </span>
      </p>

      <div class="results-grid">
        <section class="card card--source">
          <h2 class="card__title">What you wrote</h2>
          <p class="message">{{ state.message }}</p>
        </section>

        <section class="card card--rewrite" :class="{ 'card--flat': alreadyClear }">
          <div class="card__head">
            <h2 class="card__title">{{ alreadyClear ? 'Kept as written' : 'Clearer version' }}</h2>
            <button
              v-if="state.result.rewrite"
              type="button"
              class="copy-btn"
              @click="copyRewrite"
            >
              <Check v-if="copyState === 'copied'" :size="14" :stroke-width="2" aria-hidden="true" />
              <Copy v-else :size="14" :stroke-width="2" aria-hidden="true" />
              <span aria-live="polite">{{ copyState === 'copied' ? 'Copied' : 'Copy' }}</span>
            </button>
          </div>

          <p v-if="state.result.rewrite" class="message message--rewrite">{{ state.result.rewrite }}</p>

          <!-- No rewrite: either the grounding check rejected it or the
               service could not be reached. Showing a flagged rewrite would
               be worse than showing none - it reads as finished text. -->
          <div v-else class="blocked">
            <strong>No rewrite for this messgae</strong>
            <p>
              {{
                state.result.degraded_reason?.length
                  ? 'Your message is clear enough! No changes can be done.'
                  : 'The rewriter could not be reached.'
              }}
            </p>
          </div>
        </section>
      </div>

      <section v-if="state.result.notes.length && !alreadyClear" class="card">
        <h2 class="card__title">What changed</h2>
        <ul class="notes">
          <li v-for="(note, i) in state.result.notes" :key="i">{{ note }}</li>
        </ul>
      </section>

      <section v-if="meaningRows.length" class="card">
        <h2 class="card__title">What your message is asking for</h2>
        <dl class="meaning">
          <div v-for="row in meaningRows" :key="row.label" class="meaning__row">
            <dt>{{ row.label }}</dt>
            <dd>{{ row.value }}</dd>
          </div>
        </dl>
        <p class="card__hint">
          Read from your draft, not added to it. If something here is wrong, the message probably
          says it less clearly than you meant.
        </p>
      </section>

      <div class="actions">
        <button type="button" class="btn btn--secondary" @click="startOver">Start a new message</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.compose {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1240px;
}

.intro {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 60ch;
}

.intro h1 {
  font-family: var(--font-serif);
  font-size: clamp(32px, 4.4vw, 46px);
  font-weight: 500;
  line-height: 1.08;
  letter-spacing: -0.025em;
  margin: 0;
  text-wrap: balance;
}

.intro p {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.panes {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
}

@media (min-width: 1040px) {
  .panes {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-frame);
}

.pane__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.pane__label {
  font-size: 14.5px;
  font-weight: 600;
}

.draft-box {
  width: 100%;
  flex: 1;
  min-height: 300px;
  resize: vertical;
  padding: 16px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  font-size: 15.5px;
  line-height: 1.68;
  color: var(--color-text);
}

.draft-box::placeholder {
  color: var(--color-text-muted);
  opacity: 1;
}

.draft-box:focus {
  outline: none;
  border-color: var(--color-primary);
}

.draft-box--error,
.draft-box--error:focus {
  border-color: var(--color-danger-text);
}


.pane__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.pane__buttons {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pane--preview {
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  padding: 32px 28px;
  border: 3px dashed var(--color-border-muted, #667168);
  background: var(--color-primary-soft-bg,  #FAFAF9);
}

.preview__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: var(--color-surface);
  color: var(--color-primary);
  margin-bottom: 4px;
}

.btn {
  padding: 13px 22px;
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
}

.preview__title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 500;
  letter-spacing: -0.012em;
}

.preview__note {
  margin: 0;
  max-width: 38ch;
  text-align: left;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.char-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.char-count--over {
  color: var(--color-warn-text);
  font-weight: 600;
}

.link-button {
  padding: 8px 0;
  margin: -8px 0;
  border: none;
  background: none;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--color-primary-strong-text);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.error-banner {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--color-warn-border);
  background: var(--color-warn-bg);
}

.error-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-warn-dot);
  margin-top: 7px;
  flex: none;
}

.error-banner strong {
  display: block;
  font-size: 14px;
  color: var(--color-warn-text);
}

.error-banner p {
  margin: 3px 0 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-warn-text-soft);
}

.results-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.results-header h1 {
  margin: 0 0 6px;
  font-family: var(--font-serif);
  font-size: clamp(26px, 3.2vw, 34px);
  font-weight: 500;
  letter-spacing: -0.02em;
  text-wrap: balance;
}

.results-header p {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
}

/* Advisory, and said so in the copy: three small models reading wording. */
.register {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}

.register__chip {
  padding: 4px 11px;
  border-radius: 999px;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface);
  color: var(--color-text);
}

.results-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

@media (min-width: 900px) {
  .results-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

/* The rewrite is the thing to read: the draft beside it sits back. */
.card--source {
  background: var(--color-surface-soft);
}

.card--rewrite {
  border-color: var(--color-primary-soft-border);
}

.card--flat {
  border-color: var(--color-border-soft);
}

.card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card__title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 500;
  color: var(--color-text);
}

.message {
  margin: 0;
  font-size: 15px;
  line-height: 1.7;
  white-space: pre-wrap;
  color: var(--color-text-muted);
}

.message--rewrite {
  color: var(--color-text);
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 11px;
  border-radius: 7px;
  border: 1px solid var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.blocked strong {
  display: block;
  font-size: 14px;
  color: var(--color-warn-text);
  margin-bottom: 4px;
}

.blocked p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.notes {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text);
}

.meaning {
  margin: 0;
  display: flex;
  flex-direction: column;
}

.meaning__row {
  display: grid;
  grid-template-columns: 130px minmax(0, 1fr);
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--color-border-soft);
}

.meaning__row:first-child {
  border-top: none;
  padding-top: 0;
}

.meaning dt {
  font-size: 13px;
  color: var(--color-text-faint);
}

.meaning dd {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: var(--color-text);
}

.card__hint {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-faint);
}

.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
