<script setup lang="ts">
import { ref } from 'vue'
import { useCardsStore } from '@/stores/cards'
import { useSettingsStore, type Contrast, type Typeface } from '@/stores/settings'

const settingsStore = useSettingsStore()
const cardsStore = useCardsStore()

const CONTRAST_OPTIONS: { value: Contrast; label: string }[] = [
  { value: 'soft', label: 'Soft' },
  { value: 'standard', label: 'Standard' },
  { value: 'high', label: 'High' },
]

const TYPEFACE_OPTIONS: { value: Typeface; label: string }[] = [
  { value: 'default', label: 'Default' },
  { value: 'hyperlegible', label: 'Hyperlegible' },
]

const showDeleteConfirm = ref(false)

function confirmDelete() {
  cardsStore.clear()
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
        <strong>Contrast</strong>
        <span class="row__desc">Soft is the gentlest. High is the sharpest.</span>
        <div class="options">
          <button
            v-for="opt in CONTRAST_OPTIONS"
            :key="opt.value"
            type="button"
            class="option"
            :class="{ 'option--active': settingsStore.settings.contrast === opt.value }"
            @click="settingsStore.settings.contrast = opt.value"
          >
            {{ opt.label }}
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

      <div class="row row--toggle">
        <span class="row__text">
          <strong>Calm mode</strong>
          <span class="row__desc">Removes colour accents and tints. The interface goes quiet and neutral.</span>
        </span>
        <button
          type="button"
          class="switch"
          :class="{ 'switch--on': settingsStore.settings.calm }"
          role="switch"
          :aria-checked="settingsStore.settings.calm"
          @click="settingsStore.settings.calm = !settingsStore.settings.calm"
        >
          <span class="switch__knob" />
        </button>
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
  border-top: 1px solid #f0ebe2;
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
}

.option--active {
  border-color: var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

.row--toggle {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.row__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.switch {
  width: 46px;
  height: 26px;
  flex: 0 0 46px;
  border-radius: 999px;
  border: 1px solid var(--color-border-strong);
  background: #f0ebe2;
  cursor: pointer;
  padding: 2px;
  display: flex;
  justify-content: flex-start;
}

.switch--on {
  border-color: var(--color-primary-border);
  background: var(--color-primary);
  justify-content: flex-end;
}

.switch__knob {
  width: 20px;
  height: 20px;
  border-radius: 999px;
  background: var(--color-frame);
  display: block;
  box-shadow: 0 1px 2px rgba(58, 55, 51, 0.2);
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
  color: #4a453e;
}

.btn--secondary:hover {
  background: #f6f2ea;
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
