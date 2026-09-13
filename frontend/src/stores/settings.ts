import { reactive, watchEffect } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'readtheroom.settings'

export type Typeface = 'default' | 'hyperlegible'
export type Appearance = 'light' | 'dark'
export type Accent = 'sage' | 'ocean' | 'lavender' | 'slate'
export type TextSize = 'small' | 'standard' | 'large'

interface Settings {
  typeface: Typeface
  appearance: Appearance
  accent: Accent
  textSize: TextSize
  boldText: boolean
}

const DEFAULTS: Settings = {
  typeface: 'default',
  appearance: 'light',
  accent: 'sage',
  textSize: 'standard',
  boldText: false,
}

function load(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Settings>) } : { ...DEFAULTS }
  } catch {
    return { ...DEFAULTS }
  }
}

// Comfort preferences
// Applied globally via `data-*` attributes on <html> so any component's CSS
// can key off them without prop-drilling.
export const useSettingsStore = defineStore('settings', () => {
  const settings = reactive<Settings>(load())

  watchEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    const root = document.documentElement
    root.dataset.typeface = settings.typeface
    root.dataset.appearance = settings.appearance
    root.dataset.accent = settings.accent
    root.dataset.textSize = settings.textSize
    root.dataset.boldText = String(settings.boldText)
  })

  function reset() {
    Object.assign(settings, DEFAULTS)
  }

  return { settings, reset }
})
