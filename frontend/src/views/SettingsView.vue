<script setup lang="ts">
import { ref } from 'vue'
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

const APPEARANCE_OPTIONS: { value: Appearance; label: string }[] = [
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
  showDeleteConfirm.value = false
}
</script>

<template>
  <div class="settings">
    <div class="header">
      <h2>Comfort settings</h2>
      <p>Set the room to your liking. Changes apply straight away.</p>
    </div>

    <div class="panel">
      <div class="row">
        <strong>Appearance</strong>
        <span class="row__desc">Switch between a light or dark page background.</span>
        <div class="options">
          <button
            v-for="opt in APPEARANCE_OPTIONS"
            :key="opt.value"
            type="button"
            class="option"
            :class="{ 'option--active': settingsStore.settings.appearance === opt.value }"
            @click="settingsStore.settings.appearance = opt.value"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <div class="row">
        <strong>Accent color</strong>
        <span class="row__desc">Pick the color used for highlights and active states.</span>
        <div class="options">
          <button
            v-for="opt in ACCENT_OPTIONS"
            :key="opt.value"
            type="button"
            class="option option--accent"
            :class="{ 'option--active': settingsStore.settings.accent === opt.value }"
            @click="settingsStore.settings.accent = opt.value"
          >
            <span class="swatch" :style="{ background: opt.swatch }" />
            {{ opt.label }}
          </button>
        </div>
      </div>

      <div class="row">
        <strong>Text format</strong>
        <span class="row__desc">Change how large or bold the text is. Buttons preview the effect.</span>
        <div class="options">
          <button
            v-for="opt in TEXT_SIZE_OPTIONS"
            :key="opt.value"
            type="button"
            class="option option--size"
            :class="[`option--size-${opt.value}`, { 'option--active': settingsStore.settings.textSize === opt.value }]"
            @click="settingsStore.settings.textSize = opt.value"
          >
            {{ opt.label }}
          </button>
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
        <strong>Typeface</strong>
        <span class="row__desc">Hyperlegible has more distinct letter shapes.</span>
        <div class="options">
          <button
            v-for="opt in TYPEFACE_OPTIONS"
            :key="opt.value"
            type="button"
            class="option"
            :class="{ 'option--active': settingsStore.settings.typeface === opt.value }"
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
        Delete my saved cards
      </button>
    </div>

    <div v-if="showDeleteConfirm" class="modal-backdrop" @click="showDeleteConfirm = false">
      <div class="modal" @click.stop>
        <strong>Delete your saved cards?</strong>
        <p>
          This clears every card in your Study section on this device. It can't be undone, and cards aren't backed
          up anywhere else.
        </p>
        <div class="modal-actions">
          <button type="button" class="btn btn--danger-solid" @click="confirmDelete">Delete cards</button>
          <button type="button" class="btn btn--secondary" @click="showDeleteConfirm = false">Keep them</button>
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

.header h2 {
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.015em;
  margin: 0 0 6px;
}

.header p {
  margin: 0;
  font-size: 14px;
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

.btn--secondary {
  border: 1px solid var(--color-border-strong);
  background: var(--color-frame);
  color: var(--color-text);
}

.btn--secondary:hover {
  background: var(--color-surface-soft);
}

.btn--danger {
  border: 1px solid var(--color-warn-border);
  background: var(--color-frame);
  color: var(--color-warn-text);
}

.btn--danger:hover {
  background: var(--color-warn-bg);
}

.btn--danger-solid {
  border: 1px solid var(--color-warn-text);
  background: var(--color-warn-text);
  color: var(--color-frame);
}

.btn--danger-solid:hover {
  background: #574a3c;
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
