<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Check, Copy } from '@lucide/vue'
import { decodeMessage, EmptyMessageError, MAX_MESSAGE_LENGTH, MessageTooLongError } from '@/services/decodeService'
import { findLocalPatternMatch } from '@/services/localPatterns'
import { getPatterns } from '@/services/patternsService'
import { reviewMessage } from '@/services/reviewService'
import { useCardsStore } from '@/stores/cards'
import { useDecodesStore } from '@/stores/decodes'
import { ELEMENT_LABELS, NOT_SPECIFIED, type DecodeResult, type ElementKey } from '@/types/decode'
import type { Pattern, SavedCard } from '@/types/pattern'
import type { DecodeRecord } from '@/types/decode'
import { REVIEW_FIELD_LABELS, type FullReview, type ReviewField } from '@/types/review'

const cardsStore = useCardsStore()
const decodesStore = useDecodesStore()

const SAMPLE =
  "Hi,\n\nWhen you get a chance, could you take a look at the Q3 deck and tighten up the numbers section? Would be great to have it before the leadership sync.\n\nAlso, loop in whoever owns the pricing slide if that's easier.\n\nThanks!"

const state = reactive({
  message: '',
  error: '',
  loading: false,
  result: null as DecodeResult | null,
  checked: new Set<ElementKey>(),
  matchedPattern: null as Pattern | null,
  record: null as DecodeRecord | null,
  savedCard: null as SavedCard | null,
  showSaved: false,
  // The model-backed reading. Arrives seconds after the instant decode above,
  // so it is tracked separately and rendered only once it lands - the page is
  // never blocked waiting for it.
  llm: null as FullReview | null,
  llmLoading: false,
})

async function review() {
  const text = state.message.trim()
  if (!text) {
    state.error = 'The box is empty. Paste a message and we will go through it together.'
    return
  }

  state.error = ''
  state.loading = true
  try {
    state.result = await decodeMessage(text)
    state.checked = new Set()
    state.matchedPattern = null
    if (state.result.category) {
      const patterns = await getPatterns()
      const candidates = patterns.filter((p) => p.category === state.result!.category)
      // Prefer the specific pattern the wording actually points to. Only
      // fall back to "the one candidate in this category" when there's no
      // ambiguity to begin with — never guess between several.
      const specific = findLocalPatternMatch(text)
      state.matchedPattern =
        candidates.find((p) => p.id === specific?.id) ?? (candidates.length === 1 ? (candidates[0] ?? null) : null)
    }
    // Keep the decode so the work survives the session and a card can point
    // back at the message. Local only - see stores/decodes.ts.
    state.record = decodesStore.save(text, state.result, state.matchedPattern?.id ?? null)
    
    // Deliberately not awaited. The decode above is already on screen; this
    // takes seconds and fills in the closer reading when it arrives. It
    // resolves to a degraded result rather than throwing, so it can never
    // break a decode that already worked.
    state.llm = null
    state.llmLoading = true
    void reviewMessage(text)
      .then((result) => {
        // Ignore a late reply for a message the user has moved on from.
        if (state.message.trim() === text) state.llm = result
      })
      .finally(() => {
        // Unguarded on purpose. The guard above stops a stale reading being
        // shown; this flag must clear either way, or editing the message
        // mid-request leaves the spinner running forever.
        state.llmLoading = false
      })
  } catch (err) {
    // The decoder decides what counts as a message - one rule, server-side,
    // mirrored offline. See decodeService.
    state.result = null
    state.record = null
    if (err instanceof EmptyMessageError) {
      state.error = 'This does not look like a message yet. Paste the message text itself and try again.'
    } else if (err instanceof MessageTooLongError) {
      state.error = err.message
    } else {
      throw err
    }
  } finally {
    state.loading = false
  }
}

/** Claims worth showing: those with a reading, in a stable field order. */
const llmClaims = computed(() => {
  const order: ReviewField[] = [
    'purpose', 'required_action', 'responsible_person', 'deadline', 'priority', 'context',
  ]
  return [...(state.llm?.claims ?? [])]
    .filter((c) => c.text?.trim())
    .sort((a, b) => order.indexOf(a.field) - order.indexOf(b.field))
    .map((c) => ({
      ...c,
      label: REVIEW_FIELD_LABELS[c.field] ?? c.field,
    }))
})

function reset() {
  state.message = ''
  state.error = ''
  state.result = null
  // The closer reading belongs to the message that was cleared.
  state.llm = null
  state.llmLoading = false
  state.checked = new Set()
  state.matchedPattern = null
  state.record = null
  state.showSaved = false
}

// F7: explicit, opt-in save. A card is saved even with no library match —
// what the message left unsaid is the lesson either way.
function makeFlashcard() {
  if (!state.record) return
  state.savedCard = cardsStore.save(state.record, state.matchedPattern)
  state.showSaved = true
}

function loadSample() {
  state.message = SAMPLE
  state.error = ''
}

function editMessage() {
  state.result = null
}

function toggleChecked(field: ElementKey) {
  if (state.checked.has(field)) state.checked.delete(field)
  else state.checked.add(field)
  // Remember which questions the user judged worth asking.
  if (state.record) decodesStore.setAsked(state.record.id, [...state.checked])
}

// "What's covered" duplicated the asks above it: the Task-To-Do row is the
// same sentence as the first bullet, so the panel often showed one row that
// said nothing new. Rows already stated as an ask are dropped, and the panel
// hides entirely when none survive.
const coveredRows = computed(() => {
  if (!state.result) return []
  const asks = new Set(todo.value.map((t) => t.text.trim().toLowerCase()))
  return state.result.covered
    .map((field) => ({
      field,
      label: ELEMENT_LABELS[field],
      value: state.result!.elements[field],
    }))
    .filter((row) => !asks.has(row.value.trim().toLowerCase()))
})

// One bullet per ask. Falls back to the single-task view when the offline
// decoder answered, which has no `tasks` array.
const todo = computed(() => {
  if (!state.result) return []

  const tasks = state.result.tasks ?? []
  if (tasks.length) {
    return tasks.map((task) => {
      const known = [
        task.deadline !== NOT_SPECIFIED ? `by ${task.deadline}` : null,
        task.for_whom !== NOT_SPECIFIED ? `for ${task.for_whom}` : null,
        task.time !== NOT_SPECIFIED ? `at ${task.time}` : null,
      ].filter(Boolean)
      return { text: task.text, detail: known.join(' · ') }
    })
  }

  const single = state.result.elements.task
  return single && single !== NOT_SPECIFIED ? [{ text: single, detail: '' }] : []
})

const checkedPrompts = computed(() => {
  if (!state.result) return []
  return state.result.missing.filter((item) => state.checked.has(item.field))
})

const copyState = ref<'idle' | 'copied' | 'failed'>('idle')
let copyResetTimer: ReturnType<typeof setTimeout> | undefined

async function copyPromptsToClipboard() {
  const text = checkedPrompts.value.map((q) => q.prompt).join('\n')
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
  <div class="decode">
    <div v-if="!state.result" class="intake">
      <div class="intro">
        <h2>Paste the message</h2>
        <p>An email, a Slack message, a note from your manager...</p>
      </div>

      <div class="input-area">
        <textarea
          v-model="state.message"
          placeholder="Hi, when you get a chance, could you take a look at…"
          spellcheck="false"
          :class="{ 'input-area__box--error': !!state.error }"
          class="input-area__box"
        />
        <div class="input-area__footer">
          <button type="button" class="link-button" @click="loadSample">Use a sample message</button>
          <span class="char-count" :class="{ 'char-count--over': state.message.length > MAX_MESSAGE_LENGTH }">
            {{ state.message.length }} / {{ MAX_MESSAGE_LENGTH }}
          </span>
        </div>
      </div>

      <div v-if="state.error" class="error-banner">
        <span class="error-dot" />
        <div>
          <strong>Please enter an actual message</strong>
          <p>{{ state.error }}</p>
        </div>
      </div>

      <div class="actions">
        <button type="button" class="btn btn--primary" :disabled="state.loading" @click="review">
          {{ state.loading ? 'Decoding...' : 'Decode Message' }}
        </button>
        <button type="button" class="btn btn--secondary" @click="reset">Reset</button>
      </div>
    </div>

    <template v-else>
      <div class="results-header">
        <div>
          <h2>Here's what the message says</h2>
          <p>What's stated stays visible. What's unclear stays open.</p>
        </div>
        <button type="button" class="btn btn--ghost" @click="editMessage">Edit message</button>
      </div>

      <div class="results-grid">
        <div class="original-panel">
          <p>{{ state.message }}</p>
        </div>

        <div class="findings">
          <div v-if="todo.length" class="panel panel--todo">
            <div class="panel__header panel__header--todo">
              <span class="panel-dot panel-dot--todo" />
              <strong>What you're being asked to do</strong>
            </div>
            <div class="panel__body">
              <ul class="todo">
                <li v-for="(item, i) in todo" :key="i" class="todo__item">
                  <span class="todo__text">{{ item.text }}</span>
                  <span v-if="item.detail" class="todo__detail">{{ item.detail }}</span>
                </li>
              </ul>
            </div>
          </div>

          <div v-if="coveredRows.length" class="panel panel--covered">
            <div class="panel__header panel__header--covered">
              <span class="panel-dot panel-dot--covered" />
              <strong>What's covered</strong>
            </div>
            <div class="panel__body">
              <div v-for="row in coveredRows" :key="row.field" class="row">
                <span class="row__label">{{ row.label }}</span>
                <span class="row__value">{{ row.value }}</span>
              </div>
            </div>
          </div>

          <div class="panel panel--missing">
            <div class="panel__header panel__header--missing">
              <div class="panel__header-title">
                <span class="panel-dot panel-dot--missing" />
                <strong>What's missing</strong>
              </div>
              <span class="hint">tick what matters to you</span>
            </div>
            <div class="panel__body panel__body--flush">
              <button
                v-for="gap in state.result.missing"
                :key="gap.field"
                type="button"
                class="gap-row"
                :class="{ 'gap-row--checked': state.checked.has(gap.field) }"
                @click="toggleChecked(gap.field)"
              >
                <span class="checkbox" :class="{ 'checkbox--checked': state.checked.has(gap.field) }">
                  <span v-if="state.checked.has(gap.field)" class="checkbox__mark" />
                </span>
                <span class="gap-row__text">
                  <strong>{{ ELEMENT_LABELS[gap.field] }} not specified</strong>
                  <span>{{ gap.prompt }}</span>
                </span>
              </button>
              <div v-if="!state.result.missing.length" class="gap-row gap-row--empty">
                <span>Every element was stated in the message.</span>
              </div>
            </div>
          </div>

          <!-- The model-backed reading. Appears only once it arrives, so the
               decode above is never held up waiting for it. Every claim here
               was verified server-side against the original message; anything
               that could not be traced back was dropped before it got here. -->
          <div v-if="state.llmLoading || state.llm" class="panel panel--reading">
            <div class="panel__header panel__header--reading">
              <span class="panel-dot panel-dot--reading" />
              <strong>A closer reading</strong>
              <span v-if="state.llmLoading" class="reading__status">reading…</span>
              <span
                v-else-if="state.llm?.degraded"
                class="reading__status reading__status--degraded"
                title="The model's answer could not be verified against your message, so only what was read directly from the text is shown."
              >limited</span>
            </div>

            <!-- The model takes seconds. An empty bordered box under a
                 header reads as broken, so hold the shape with placeholder
                 lines until real content replaces them. -->
            <div v-if="state.llmLoading && !state.llm" class="panel__body">
              <div class="skeleton skeleton--wide" />
              <div class="skeleton skeleton--wide" />
              <div class="skeleton" />
            </div>

            <div v-if="state.llm" class="panel__body">
              <p v-if="state.llm.summary" class="reading__summary">{{ state.llm.summary }}</p>

              <!-- Reading first, quote second. The quote is often the same
                   phrase the decode panels above already show; what the model
                   adds is what it means, so that leads and the quote becomes
                   the citation underneath it. -->
              <div v-for="(c, i) in llmClaims" :key="i" class="reading__claim">
                <p class="reading__insight">{{ c.reading || c.text }}</p>
                <p v-if="c.reading" class="reading__source">
                  <span class="reading__field">{{ c.label }}</span>
                  <span class="reading__quote">“{{ c.text }}”</span>
                </p>
              </div>

              <div v-if="state.llm.unstated?.length" class="reading__unstated">
                <span class="reading__label">Questions worth asking</span>
                <ul>
                  <li v-for="(q, i) in state.llm.unstated" :key="i">{{ q }}</li>
                </ul>
              </div>

              <p v-if="state.llm.degraded" class="reading__degraded-note">
                Showing only what could be read directly from your message.
              </p>
            </div>
          </div>

          <div v-if="checkedPrompts.length" class="panel panel--confirm">
            <div class="confirm-header">
              <strong>Before you reply, ask</strong>
              <button type="button" class="copy-btn" @click="copyPromptsToClipboard">
                <Check v-if="copyState === 'copied'" :size="14" :stroke-width="2" aria-hidden="true" />
                <Copy v-else :size="14" :stroke-width="2" aria-hidden="true" />
                {{ copyState === 'copied' ? 'Copied' : copyState === 'failed' ? "Couldn't copy" : 'Copy' }}
              </button>
            </div>
            <div class="confirm-list">
              <div v-for="q in checkedPrompts" :key="q.field" class="confirm-item">
                {{ q.prompt }}
              </div>
            </div>
          </div>

          <div v-if="!state.matchedPattern" class="notice">
            <span class="notice-dot" />
            <div>
              <strong>No library match for this wording</strong>
              <span>
                You can still keep this card, it will show the message and what it left
                unsaid, without a pattern explanation.
                <RouterLink to="/library">Browse the library</RouterLink> to see what is covered so far.
              </span>
            </div>
          </div>

          <div class="actions">
            <button
              v-if="state.record"
              type="button"
              class="btn btn--primary"
              @click="makeFlashcard"
            >
              Make it a Flashcard
            </button>
            <button type="button" class="btn btn--secondary" @click="reset">Start a new message</button>
          </div>
          <span v-if="state.matchedPattern" class="disclaimer">
            Or leaving this page without save a Flashcard :)
          </span>
        </div>
      </div>
    </template>

    <div v-if="state.showSaved" class="modal-backdrop" @click="state.showSaved = false">
      <div class="modal" @click.stop>
        <div class="modal__title">
          <span class="modal__dot" />
          <strong>Flashcard created</strong>
        </div>
        <div class="modal__card">
          <strong>{{ state.savedCard?.name }}</strong>
          <span>{{ state.savedCard?.implies }}</span>
        </div>
        <p class="modal__note">It's in your Study section whenever you want it.</p>
        <div class="actions">
          <RouterLink to="/study" class="btn btn--primary">View in Study</RouterLink>
          <button type="button" class="btn btn--secondary" @click="state.showSaved = false">Keep reading</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.decode {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.intake {
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.intro {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.intro h2 {
  font-family: var(--font-serif);
  font-size: 27px;
  font-weight: 500;
  letter-spacing: -0.015em;
  margin: 0;
}

.intro p {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.input-area {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.input-area__box {
  width: 100%;
  min-height: 262px;
  resize: vertical;
  padding: 18px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  font-size: 15.5px;
  line-height: 1.68;
  color: var(--color-text);
  outline: none;
}

.input-area__box:focus {
  border-color: var(--color-primary);
}

.input-area__box--error {
  border-color: #d8c9b8;
}

.input-area__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.char-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-faint);
  white-space: nowrap;
}

.char-count--over {
  color: var(--color-warn-text);
  font-weight: 600;
}

.link-button {
  align-self: flex-start;
  background: none;
  border: none;
  padding: 0;
  font-size: 13.5px;
  color: var(--color-primary);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.error-banner {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--color-warn-bg);
  border: 1px solid var(--color-warn-border);
}

.error-banner strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-warn-text);
  display: block;
}

.error-banner p {
  margin: 3px 0 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-warn-text-soft);
}

.error-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-warn-dot);
  margin-top: 7px;
  flex: 0 0 7px;
}

.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 2px;
}

.btn {
  padding: 13px 22px;
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.7;
  cursor: default;
}

.btn--primary {
  border: 1px solid var(--color-primary-border);
  background: var(--color-primary);
  color: var(--color-frame);
}

.btn--primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn--secondary {
  padding: 13px 20px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-frame);
  color: #4a453e;
}

.btn--secondary:hover {
  background: #f6f2ea;
}

.btn--ghost {
  padding: 8px 14px;
  border: 1px solid var(--color-border-strong);
  background: none;
  border-radius: 8px;
  font-size: 13.5px;
  color: #4a453e;
  cursor: pointer;
}

.btn--ghost:hover {
  background: #f6f2ea;
}

.results-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.results-header h2 {
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.015em;
  margin: 0 0 6px;
}

.results-header p {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.results-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.85fr) 1.15fr;
  gap: 20px;
  align-items: start;
}

@media (max-width: 720px) {
  .results-grid {
    grid-template-columns: 1fr;
  }
}

.original-panel {
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface-soft);
  padding: 18px;
}

/* Follows the scroll on desktop's two-column layout, stopping clear of the
   sticky app header (64px) - stays put while the longer analysis column
   scrolls past it. Mobile stacks the panels instead, so nothing sticks there. */
@media (min-width: 721px) {
  .original-panel {
    position: sticky;
    top: 80px;
    max-height: calc(100vh - 100px);
    overflow-y: auto;
  }
}

.original-panel p {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.72;
  color: #5c564d;
  white-space: pre-wrap;
}

.findings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  background: var(--color-surface);
  overflow: hidden;
}

/* The bullet list is the headline answer - it spans both columns above
   the covered/missing split. */
.panel--todo {
  grid-column: 1 / -1;
  border: 1px solid var(--color-primary-soft-border);
}

.panel__header--todo {
  background: var(--color-primary-soft-bg);
}

.panel-dot--todo {
  background: var(--color-primary);
}

.todo {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.todo__item {
  line-height: 1.5;
}

.todo__text {
  display: block;
}

.todo__detail {
  display: block;
  font-family: var(--font-mono);
  font-size: 12px;
  opacity: 0.7;
  margin-top: 2px;
}

.panel--covered {
  border: 1px solid var(--color-primary-soft-border);
}

.panel--missing {
  border: 1px solid var(--color-warn-border);
}

.panel__header {
  padding: 15px 18px;
  display: flex;
  align-items: center;
  gap: 9px;
}

.panel__header--covered {
  background: var(--color-primary-soft-bg);
}

.panel__header--missing {
  background: var(--color-warn-bg);
  justify-content: space-between;
}

.panel__header-title {
  display: flex;
  align-items: center;
  gap: 9px;
}

.panel-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
}

.panel-dot--covered {
  background: var(--color-primary);
}

.panel-dot--missing {
  background: var(--color-warn-dot);
}

.hint {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-faint);
}

.panel__body {
  display: flex;
  flex-direction: column;
}

.row {
  display: grid;
  grid-template-columns: 132px 1fr;
  gap: 14px;
  padding: 13px 18px;
  border-top: 1px solid #f0ebe2;
}

.row__label {
  font-size: 13px;
  color: var(--color-text-faint);
  padding-top: 1px;
}

.row__value {
  font-size: 14.5px;
  line-height: 1.55;
  color: var(--color-text);
}

.row__value--muted {
  color: var(--color-text-faint);
}

.panel__body--flush .gap-row:first-child {
  border-top: none;
}

.gap-row {
  display: flex;
  gap: 13px;
  align-items: flex-start;
  text-align: left;
  width: 100%;
  padding: 14px 18px;
  border: none;
  border-top: 1px solid #f0ebe2;
  cursor: pointer;
  background: none;
  /* F23: the covered/missing split does not rely on color alone —
     a dashed left border marks a missing row independent of hue. */
  border-left: 3px dashed var(--color-warn-border);
}

.gap-row--checked {
  background: #f7faf8;
}

.gap-row--empty {
  cursor: default;
  border-left: none;
  color: var(--color-text-muted);
  font-size: 14px;
}

.checkbox {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  margin-top: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border-strong);
  background: var(--color-surface);
}

.checkbox--checked {
  border-color: var(--color-primary);
  background: var(--color-primary-soft-bg);
}

.checkbox__mark {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: var(--color-primary);
  display: block;
}

.gap-row__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.gap-row__text strong {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--color-text);
}

.gap-row__text span {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.panel--confirm {
  border: 1px solid var(--color-border);
  background: var(--color-surface-soft);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel--confirm strong {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--color-text);
}

.confirm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
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

.copy-btn:hover {
  border-color: var(--color-primary-border);
}

.confirm-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.confirm-item {
  padding-left: 14px;
  border-left: 2px solid var(--color-primary-soft-border);
  font-size: 14px;
  line-height: 1.55;
  color: #4a453e;
}

.disclaimer {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--color-text-faint);
}

.notice {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  background: var(--color-surface-soft);
  border: 1px solid var(--color-border-soft);
}

.notice-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-text-faint);
  margin-top: 7px;
  flex: 0 0 7px;
}

.notice strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  display: block;
}

.notice span {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(58, 55, 51, 0.28);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 40;
}

.modal {
  width: 100%;
  max-width: 430px;
  background: var(--color-frame);
  border: 1px solid var(--color-border-strong);
  border-radius: 16px;
  padding: 26px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: 0 18px 44px rgba(58, 55, 51, 0.16);
}

.modal__title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal__title strong {
  font-family: var(--font-serif);
  font-size: 21px;
  font-weight: 500;
  color: var(--color-text);
}

.modal__dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--color-primary);
}

.modal__card {
  border: 1px solid var(--color-border-soft);
  border-radius: 12px;
  background: var(--color-surface-soft);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.modal__card strong {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.modal__card span {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.modal__note {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

/* A closer reading - the model-backed panel. Muted next to the decode panels
   on purpose: it arrives later and is advisory, so it should not compete with
   the findings the user already has. */
.panel--reading { border-color: var(--border, #e3e3e3); }
.panel__header--reading { display: flex; align-items: center; gap: 0.5rem; }
.panel-dot--reading { background: #7c6cf0; }
.reading__status {
  margin-left: auto; font-size: 0.78rem; opacity: 0.7; font-weight: 500;
}
.reading__status--degraded { color: #a8632b; opacity: 1; cursor: help; }
.reading__summary { margin: 0 0 0.85rem; line-height: 1.5; }
.reading__claim {
  padding: 0.6rem 0; border-top: 1px solid var(--border-subtle, #f0f0f0);
}
.reading__claim:first-of-type { border-top: 0; padding-top: 0.2rem; }
.reading__insight { margin: 0; line-height: 1.5; }
/* Same 132px label column as .row above, so the citation's field name lines
   up with "Task-To-Do" and "Time not specified" rather than sitting at its
   own arbitrary indent. */
.reading__source {
  margin: 0.35rem 0 0; font-size: 13px; color: var(--color-text-faint);
  display: grid; grid-template-columns: 132px 1fr; gap: 14px;
}
.reading__field { text-transform: lowercase; }
@media (max-width: 640px) {
  .reading__source { grid-template-columns: 1fr; gap: 0.15rem; }
}

/* Placeholder lines while the model is still working. */
.skeleton {
  height: 0.85rem; border-radius: 4px; width: 58%;
  margin: 0.55rem 0;
  background: linear-gradient(90deg,
    var(--color-surface-sunken, #f0ebe2) 25%,
    rgba(255, 255, 255, 0.55) 50%,
    var(--color-surface-sunken, #f0ebe2) 75%);
  background-size: 200% 100%;
  animation: skeleton-sweep 1.4s ease-in-out infinite;
}
.skeleton--wide { width: 100%; }
.skeleton:first-child { margin-top: 0; }
@keyframes skeleton-sweep {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; }
}
.reading__quote { font-style: italic; }
.reading__label { font-size: 0.8rem; opacity: 0.68; }
.reading__unstated { margin-top: 0.9rem; }
.reading__unstated ul { margin: 0.35rem 0 0; padding-left: 1.1rem; }
.reading__unstated li { margin-bottom: 0.3rem; line-height: 1.45; }
.reading__degraded-note {
  margin: 0.85rem 0 0; font-size: 0.85rem; opacity: 0.65;
}
@media (max-width: 640px) {
  .reading__claim { grid-template-columns: 1fr; }
  .reading__note { grid-column: 1; }
}
</style>
