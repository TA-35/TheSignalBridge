import { reactive, watchEffect } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'readtheroom.settings'

export type Contrast = 'soft' | 'standard' | 'high'
export type Typeface = 'default' | 'hyperlegible'

interface Settings {
  contrast: Contrast
  typeface: Typeface
  calm: boolean
}

const DEFAULTS: Settings = { contrast: 'standard', typeface: 'default', calm: false }

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
    root.dataset.contrast = settings.contrast
    root.dataset.typeface = settings.typeface
    root.dataset.calm = String(settings.calm)
  })

  function reset() {
    Object.assign(settings, DEFAULTS)
  }

  return { settings, reset }
})
