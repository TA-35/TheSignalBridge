<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useAccountStore } from '@/stores/account'
import { useActivityStore } from '@/stores/activity'
import { useCardsStore } from '@/stores/cards'
import { useDecodesStore } from '@/stores/decodes'
import {
  useSettingsStore,
  type Accent,
  type Appearance,
  type TextSize,
  type Typeface,
} from '@/stores/settings'

const settingsStore = useSettingsStore()
const cardsStore = useCardsStore()
const decodesStore = useDecodesStore()
const activityStore = useActivityStore()
const accountStore = useAccountStore()

const APPEARANCE_OPTIONS: { value: Appearance; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

const ACCENT_OPTIONS: { value: Accent; label: string; swatch: string }[] = [
  { value: 'sage', label: 'Sage', swatch: '#4f7a69' },
  { value: 'ocean', label: 'Ocean', swatch: '#3d6fa0' },
  { value: 'lavender', label: 'Lavender', swatch: '#7d6a9e' },
  { value: 'slate', label: 'Slate', swatch: '#5c6570' },
]

const TEXT_SIZE_OPTIONS: { value: TextSize; label: string }[] = [
  { value: 'small', label: 'A-' },
  { value: 'standard', label: 'A' },
  { value: 'large', label: 'A+' },
]

const TYPEFACE_OPTIONS: { value: Typeface; label: string }[] = [
  { value: 'default', label: 'Default' },
  { value: 'hyperlegible', label: 'Hyperlegible' },
]

const showDeleteConfirm = ref(false)

function confirmDelete() {
  cardsStore.clear()
  // Decodes hold the message text - clearing cards alone would leave it.
  decodesStore.clear()
  // Progress too: days opened, focus sessions and what was typed for them,
  // phrases viewed, cards reviewed, and the dashboard's display flags. Signed
  // in, the account's copy goes as well, or it would sync straight back.
  activityStore.clearAll()
  showDeleteConfirm.value = false
}

// The delete confirmation.
//
// It guards the one irreversible action in the app, so it has to behave like a
// dialog and not merely look like one. Before this, nothing announced that it
// had opened, Escape did nothing, and the first Tab from the trigger landed on
// "Delete cards" - so trigger, Tab, Enter wiped every saved card without the
// warning ever being read out.
const confirmModal = ref<HTMLElement | null>(null)
let lastFocused: HTMLElement | null = null

function closeDeleteConfirm() {
  showDeleteConfirm.value = false
}

watch(showDeleteConfirm, async (open) => {
  if (open) {
    lastFocused = document.activeElement as HTMLElement | null
    await nextTick()
    // Focus the dialog itself rather than either button: landing on "Delete
    // cards" is how a confirmation becomes a trapdoor.
    confirmModal.value?.focus()
    return
  }
  if (lastFocused && document.contains(lastFocused)) lastFocused.focus()
  lastFocused = null
})

const FOCUSABLE =
  'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])'

function trapTab(event: KeyboardEvent) {
  const root = confirmModal.value
  if (!root) return
  const items = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (el) => el.offsetParent !== null,
  )
  if (!items.length) return
  const first = items[0]!
  const last = items[items.length - 1]!
  const active = document.activeElement
  if (event.shiftKey && (active === first || active === root)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}
</script>

<template>
  <div class="settings">
    <div class="header">
      <h1>Comfort settings</h1>
      <p>Set the website style to your liking. Changes apply straight away.</p>
    </div>

    <div class="panel">
      <div class="row">
        <strong id="label-appearance">Appearance</strong>
        <span class="row__desc">System follows your device setting. Light and dark override it.</span>
        <div class="options" role="group" aria-labelledby="label-appearance">
          <button
            v-for="opt in APPEARANCE_OPTIONS"
            :key="opt.value"
            type="button"
            class="option"
            :class="{ 'option--active': settingsStore.settings.appearance === opt.value }"
            :aria-pressed="settingsStore.settings.appearance === opt.value"
            @click="settingsStore.settings.appearance = opt.value"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <div class="row">
        <strong id="label-accent">Accent color</strong>
        <span class="row__desc">Pick the color used for highlights and active states.</span>
        <div class="options" role="group" aria-labelledby="label-accent">
          <button
            v-for="opt in ACCENT_OPTIONS"
            :key="opt.value"
            type="button"
            class="option option--accent"
            :class="{ 'option--active': settingsStore.settings.accent === opt.value }"
            :aria-pressed="settingsStore.settings.accent === opt.value"
            @click="settingsStore.settings.accent = opt.value"
          >
            <span class="swatch" :style="{ background: opt.swatch }" />
            {{ opt.label }}
          </button>
        </div>
      </div>

      <div class="row">
        <strong id="label-text-format">Text format</strong>
        <span class="row__desc">Change how large or bold the text is. Buttons preview the effect.</span>
        <!-- Two different kinds of control used to sit in one undivided row:
             three sizes you pick between, and Bold, which is independent of
             all of them. Bold read as a fourth size. Separating them is both
             the visual fix and the one that gives each group its own name. -->
        <div class="options">
          <span class="options__set" role="group" aria-label="Text size">
            <button
              v-for="opt in TEXT_SIZE_OPTIONS"
              :key="opt.value"
              type="button"
              class="option option--size"
              :class="[`option--size-${opt.value}`, { 'option--active': settingsStore.settings.textSize === opt.value }]"
              :aria-pressed="settingsStore.settings.textSize === opt.value"
              @click="settingsStore.settings.textSize = opt.value"
            >
              {{ opt.label }}
            </button>
          </span>

          <span class="options__divider" aria-hidden="true" />

          <button
            type="button"
            class="option option--bold"
            :class="{ 'option--active': settingsStore.settings.boldText }"
            :aria-pressed="settingsStore.settings.boldText"
            @click="settingsStore.settings.boldText = !settingsStore.settings.boldText"
          >
            Bold
          </button>
        </div>
      </div>

      <div class="row">
        <strong id="label-typeface">Typeface</strong>
        <span class="row__desc">Hyperlegible has more distinct letter shapes.</span>
        <div class="options" role="group" aria-labelledby="label-typeface">
          <button
            v-for="opt in TYPEFACE_OPTIONS"
            :key="opt.value"
            type="button"
            class="option"
            :class="{ 'option--active': settingsStore.settings.typeface === opt.value }"
            :aria-pressed="settingsStore.settings.typeface === opt.value"
            @click="settingsStore.settings.typeface = opt.value"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>
    </div>

    <div class="actions">
      <button type="button" class="btn btn--secondary" @click="settingsStore.reset">
        Reset settings
      </button>
      <button type="button" class="btn btn--danger" @click="showDeleteConfirm = true">
        Delete my cards and progress
      </button>
    </div>

    <div v-if="showDeleteConfirm" class="modal-backdrop" @click="closeDeleteConfirm">
      <div
        ref="confirmModal"
        class="modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-delete-title"
        aria-describedby="confirm-delete-body"
        tabindex="-1"
        @click.stop
        @keydown.esc="closeDeleteConfirm"
        @keydown.tab="trapTab"
      >
        <strong id="confirm-delete-title">Delete your cards and progress?</strong>
        <div id="confirm-delete-body" class="modal-body">
          <p>
            This clears every card in your Study section, your decode history, and your progress on this device:
            days opened, focus sessions and what you typed for them, phrases viewed and cards reviewed. It can't be
            undone.
          </p>
          <p v-if="accountStore.signedIn">
            Your account's copy of your library cards and progress is cleared too. Another device you use keeps its
            own copy until you clear it there.
          </p>
        </div>
        <div class="modal-actions">
          <button type="button" class="btn btn--danger-solid" @click="confirmDelete">Delete everything</button>
          <button type="button" class="btn btn--secondary" @click="closeDeleteConfirm">Keep them</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings {
  max-width: 620px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 60ch;
}

.header h1 {
  font-family: var(--font-serif);
  font-size: clamp(32px, 4.4vw, 46px);
  font-weight: 500;
  line-height: 1.08;
  letter-spacing: -0.025em;
  margin: 0;
  text-wrap: balance;
}

.header p {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.panel {
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
}

.row {
  padding: 18px 20px;
  border-top: 1px solid var(--color-border-soft);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.row:first-child {
  border-top: none;
}

.row strong {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--color-text);
}

.row__desc {
  font-size: 13px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.options__set {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.options__divider {
  width: 1px;
  align-self: stretch;
  margin: 2px 4px;
  background: var(--color-border);
}

.options {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.option {
  padding: 9px 16px;
  border-radius: var(--radius-sm);
  font-size: 13.5px;
  cursor: pointer;
  border: 1px solid var(--color-border);
  background: var(--color-frame);
  color: var(--color-text-muted);
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.option--active {
  border-color: var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

.swatch {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  flex: 0 0 12px;
}

.option--size-small {
  font-size: 12px;
}

.option--size-standard {
  font-size: 15px;
}

.option--size-large {
  font-size: 19px;
}

.option--bold {
  font-weight: 700;
}

.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.btn {
  padding: 11px 18px;
  border-radius: var(--radius-sm);
  font-size: 13.5px;
  cursor: pointer;
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
  max-width: 420px;
  background: var(--color-frame);
  border: 1px solid var(--color-border-strong);
  border-radius: 16px;
  padding: 26px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  box-shadow: 0 18px 44px rgba(58, 55, 51, 0.16);
}

.modal strong {
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 500;
  color: var(--color-text);
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.modal p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.modal-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 4px;
}
</style>
