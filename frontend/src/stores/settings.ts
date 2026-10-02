import { computed, onScopeDispose, reactive, ref, watchEffect } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'readtheroom.settings'

export type Typeface = 'default' | 'hyperlegible'
// 'system' is the default and follows the OS. The previous default was a
// hardcoded 'light', so someone whose machine is in dark mode got a light site
// until they found this page - which is the exact thing an in-app appearance
// setting is warned about: it looks like the app ignoring them.
export type Appearance = 'system' | 'light' | 'dark'
export type ResolvedAppearance = 'light' | 'dark'
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
  appearance: 'system',
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
const DARK_QUERY = '(prefers-color-scheme: dark)'

export const useSettingsStore = defineStore('settings', () => {
  const settings = reactive<Settings>(load())

  // What the OS currently says, kept live: someone who switches their machine
  // to dark at sunset should see this follow without a reload.
  const mql = typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia(DARK_QUERY)
    : null
  const systemDark = ref(mql?.matches ?? false)

  if (mql) {
    const onChange = (event: MediaQueryListEvent) => {
      systemDark.value = event.matches
    }
    mql.addEventListener('change', onChange)
    onScopeDispose(() => mql.removeEventListener('change', onChange))
  }

  // What is actually painted. Everything that needs to branch on light vs dark
  // - the wordmark asset, for one - has to read this and not `settings`,
  // because 'system' is a preference, not an appearance.
  const appearance = computed<ResolvedAppearance>(() =>
    settings.appearance === 'system' ? (systemDark.value ? 'dark' : 'light') : settings.appearance,
  )

  watchEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    const root = document.documentElement
    root.dataset.typeface = settings.typeface
    root.dataset.appearance = appearance.value
    root.dataset.accent = settings.accent
    root.dataset.textSize = settings.textSize
    root.dataset.boldText = String(settings.boldText)
  })

  function reset() {
    Object.assign(settings, DEFAULTS)
  }

  return { settings, appearance, reset }
})
