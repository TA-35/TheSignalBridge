<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { BookOpen, Home, Library, LogIn, PenLine, MailQuestionMark, Settings } from '@lucide/vue'
import { useSettingsStore } from '@/stores/settings'
import logoLight from '@/assets/logo.png'
import logoDark from '@/assets/logo-dark.png'

const settingsStore = useSettingsStore()
// The wordmark's ink color is baked into the PNG - swap the whole asset
// rather than filtering it, so the sage-green mark keeps its brand color
// instead of being flattened by a brightness/invert filter.
// `appearance` is the resolved value, not the preference: with the default
// 'system' setting, `settings.appearance` is never 'dark' and the wordmark
// would stay on its light asset over a dark header.
const logoUrl = computed(() => (settingsStore.appearance === 'dark' ? logoDark : logoLight))

// `soon` marks a section that is routed and navigable but not built yet.
// Leaving those two looking like every other destination is what made the
// nav promise seven features and deliver five - and the home page's own
// secondary call to action pointed at one of them.
const navItems = [
  { to: '/', label: 'Home', icon: Home, soon: false },
  { to: '/decode', label: 'Decoder', icon: MailQuestionMark, soon: false },
  { to: '/compose', label: 'Compose', icon: PenLine, soon: true },
  { to: '/study', label: 'Study', icon: BookOpen, soon: false },
  { to: '/library', label: 'Library', icon: Library, soon: false },
  { to: '/settings', label: 'Settings', icon: Settings, soon: false },
  { to: '/login', label: 'Login', icon: LogIn, soon: true },
]

const route = useRoute()
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))

const menuOpen = ref(false)
const navEl = ref<HTMLElement | null>(null)
const toggleEl = ref<HTMLButtonElement | null>(null)

watch(
  () => route.path,
  () => {
    menuOpen.value = false
  },
)

// The menu covers the page on a phone, so the two ways people expect to get
// out of it have to work: tapping away from it, and Escape. Neither did - the
// only exits were the toggle itself and navigating somewhere.
function onDocumentPointerDown(event: PointerEvent) {
  if (!menuOpen.value) return
  const target = event.target as Node | null
  if (!target) return
  if (navEl.value?.contains(target) || toggleEl.value?.contains(target)) return
  menuOpen.value = false
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !menuOpen.value) return
  menuOpen.value = false
  // Escape dismissing a menu should leave focus on the control that opened
  // it, not wherever it happened to be inside the menu.
  toggleEl.value?.focus()
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <div class="shell">
    <!-- Seven nav items stand between the top of every page and its content.
         This is the standard way out of that for anyone driving by keyboard:
         hidden until focused, first in the tab order. -->
    <a class="skip-link" href="#main-content">Skip to content</a>

    <header class="header">
      <div class="header__inner">
        <RouterLink to="/" class="brand">
          <img :src="logoUrl" alt="TheSignalBridge" class="brand__logo" />
        </RouterLink>

        <button
          ref="toggleEl"
          type="button"
          class="menu-toggle"
          :aria-expanded="menuOpen"
          aria-controls="primary-nav"
          aria-label="Toggle navigation menu"
          @click="menuOpen = !menuOpen"
        >
          <span class="menu-toggle__bar" />
          <span class="menu-toggle__bar" />
          <span class="menu-toggle__bar" />
        </button>

        <nav id="primary-nav" ref="navEl" class="nav" :class="{ 'nav--open': menuOpen }">
          <RouterLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="nav-item"
            :class="{ 'nav-item--active': isActive(item.to) }"
          >
            <component :is="item.icon" class="nav-item__icon" :size="16" :stroke-width="2" aria-hidden="true" />
            {{ item.label }}
            <!-- Said in words, not only in the dimmer styling, so it reaches
                 a screen reader too. -->
            <span v-if="item.soon" class="nav-item__soon">soon</span>
          </RouterLink>
        </nav>
      </div>
    </header>

    <main id="main-content" class="main" tabindex="-1">
      <div class="main__inner">
        <RouterView />
      </div>
    </main>

    <!-- Exists so the privacy policy is reachable from every page. A policy
         nobody can find is the same as not having one, and this is the only
         page on the site a reader might go looking for rather than navigate
         to. Kept out of the main nav because it is not a destination people
         use the product through. -->
    <footer class="site-footer">
      <div class="site-footer__inner">
        <span class="site-footer__note">A student project for FIT5120, Monash University.</span>
        <RouterLink to="/privacy" class="site-footer__link">Privacy</RouterLink>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.skip-link {
  position: absolute;
  left: 8px;
  top: 8px;
  z-index: 60;
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: var(--color-frame);
  font-size: 14px;
  font-weight: 600;
  /* Off-screen until focused rather than display:none, so it stays in the
     tab order and can be reached at all. */
  transform: translateY(-200%);
}

.skip-link:focus-visible {
  transform: translateY(0);
}

/* The <main> takes focus when the skip link is followed; it is a scroll
   target, not a control, so it should never draw a ring of its own. */
.main:focus {
  outline: none;
}

.header {
  position: sticky;
  top: 0;
  z-index: 30;
  padding: 0 24px;
  background: var(--color-frame);
  border-bottom: 1px solid var(--color-border-soft);
  box-shadow: 0 1px 2px rgba(58, 55, 51, 0.04);
}

.header__inner {
  max-width: var(--layout-max);
  margin: 0 auto;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.brand {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}

.brand__logo {
  height: 32px;
  width: auto;
  display: block;
}

.nav {
  display: flex;
  align-items: center;
  gap: 2px;
}

.nav-item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 14px;
  border-radius: var(--radius-sm);
  font-size: 14.5px;
  font-weight: 500;
  color: var(--color-text-muted);
  white-space: nowrap;
}

/* Deliberately small: it is a qualifier on the label, not a second label.
   Every pixel here is a pixel of horizontal nav, and seven items already
   most of the header. */
.nav-item__soon {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--color-surface-soft);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
}

.nav-item__icon {
  flex: 0 0 auto;
  color: currentColor;
}

.nav-item:hover {
  background: var(--color-surface-soft);
  color: var(--color-text);
}

.nav-item--active {
  font-weight: 600;
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

.menu-toggle {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-strong);
  background: var(--color-frame);
  cursor: pointer;
  flex: 0 0 auto;
}

.menu-toggle__bar {
  display: block;
  height: 2px;
  margin: 0 auto;
  width: 18px;
  background: var(--color-text);
  border-radius: 1px;
}

.main {
  flex: 1;
  padding: 32px 24px 48px;
}

.main__inner {
  max-width: var(--layout-max);
  margin: 0 auto;
}

/* 860px used to be enough for seven items; with two of them now carrying a
   qualifier it is not, and the row spilled past the viewport between 861px
   and roughly 1110px. The horizontal nav now only appears where it actually
   fits. */
@media (max-width: 1100px) {
  .menu-toggle {
    display: flex;
  }

  .nav {
    position: absolute;
    top: 64px;
    left: 0;
    right: 0;
    flex-direction: column;
    align-items: stretch;
    gap: 2px;
    background: var(--color-frame);
    border-bottom: 1px solid var(--color-border-soft);
    padding: 10px 16px 14px;
    box-shadow: 0 8px 16px rgba(58, 55, 51, 0.06);
    display: none;
  }

  .nav--open {
    display: flex;
  }

  .nav-item {
    padding: 12px 14px;
  }

  .main {
    padding: 24px 18px 32px;
  }
}

.site-footer {
  border-top: 1px solid var(--color-primary-soft-border);
  margin-top: 48px;
}

.site-footer__inner {
  max-width: var(--layout-max);
  margin: 0 auto;
  padding: 18px 24px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.site-footer__note,
.site-footer__link {
  /* muted, not faint: faint is 2.96:1 on this background and fails WCAG AA
     for text at this size. */
  font-size: 13px;
  color: var(--color-text-muted);
}

/* A standalone control in the footer rather than a link inside a sentence,
   so it gets a real target: it was 42x17. */
.site-footer__link {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 8px;
  margin: -4px -8px;
  border-radius: var(--radius-sm);
  color: var(--color-primary-strong-text);
  text-decoration: none;
}

.site-footer__link:hover,
.site-footer__link:focus-visible {
  text-decoration: underline;
}

@media (max-width: 640px) {
  .site-footer__inner {
    padding: 16px 18px;
    justify-content: center;
    text-align: center;
  }
}
</style>
