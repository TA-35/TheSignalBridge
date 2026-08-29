<script setup lang="ts">
import { computed, reactive } from 'vue'
import { decodeMessage } from '@/services/decodeService'
import { ELEMENT_LABELS, NOT_SPECIFIED, type DecodeResult, type ElementKey } from '@/types/decode'

const SAMPLE =
  "Hi,\n\nWhen you get a chance, could you take a look at the Q3 deck and tighten up the numbers section? Would be great to have it before the leadership sync.\n\nAlso, loop in whoever owns the pricing slide if that's easier.\n\nThanks!"

const state = reactive({
  message: '',
  error: '',
  loading: false,
  result: null as DecodeResult | null,
  checked: new Set<ElementKey>(),
})

const isMeaningful = (text: string) => text.length >= 12 && /[a-z]{3,}/i.test(text) && /\s/.test(text)

async function review() {
  const text = state.message.trim()
  if (!isMeaningful(text)) {
    state.error = text.length
      ? 'This does not look like a message yet. Paste the message text itself and try again.'
      : 'The box is empty. Paste a message and we will go through it together.'
    return
  }

  state.error = ''
  state.loading = true
  try {
    state.result = await decodeMessage(text)
    state.checked = new Set()
  } finally {
    state.loading = false
  }
}

function reset() {
  state.message = ''
  state.error = ''
  state.result = null
  state.checked = new Set()
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
}

const coveredRows = computed(() => {
  if (!state.result) return []
  return state.result.covered.map((field) => ({
    field,
    label: ELEMENT_LABELS[field],
    value: state.result!.elements[field],
  }))
})

const checkedPrompts = computed(() => {
  if (!state.result) return []
  return state.result.missing.filter((item) => state.checked.has(item.field))
})
</script>

<template>
  <div class="decode">
    <template v-if="!state.result">
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
        <button type="button" class="link-button" @click="loadSample">Use a sample message</button>
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
          {{ state.loading ? 'Reviewing…' : 'Review Message' }}
        </button>
        <button type="button" class="btn btn--secondary" @click="reset">Reset</button>
      </div>
    </template>

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
          <div class="panel panel--covered">
            <div class="panel__header panel__header--covered">
              <span class="panel-dot panel-dot--covered" />
              <strong>What's covered</strong>
            </div>
            <div class="panel__body">
              <div v-for="row in coveredRows" :key="row.field" class="row">
                <span class="row__label">{{ row.label }}</span>
                <span class="row__value">{{ row.value }}</span>
              </div>
              <div v-if="!coveredRows.length" class="row">
                <span class="row__label">—</span>
                <span class="row__value row__value--muted">{{ NOT_SPECIFIED }} for every element</span>
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

          <div v-if="checkedPrompts.length" class="panel panel--confirm">
            <strong>Before you reply, ask</strong>
            <div class="confirm-list">
              <div v-for="q in checkedPrompts" :key="q.field" class="confirm-item">
                {{ q.prompt }}
              </div>
            </div>
          </div>

          <div class="actions">
            <button type="button" class="btn btn--secondary" @click="reset">Start a new message</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.decode {
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
  border-radius: var(--radius-md);
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
  border-radius: var(--radius-md);
  background: var(--color-surface);
  overflow: hidden;
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
  border-radius: 5px;
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
</style>
