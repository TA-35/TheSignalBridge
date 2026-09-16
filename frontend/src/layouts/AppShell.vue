<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { BookOpen, Home, Library, LogIn, PenLine, MailQuestionMark, Settings } from '@lucide/vue'
import { useSettingsStore } from '@/stores/settings'
import logoLight from '@/assets/logo.png'
import logoDark from '@/assets/logo-dark.png'

const settingsStore = useSettingsStore()
// The wordmark's ink color is baked into the PNG - swap the whole asset
// rather than filtering it, so the sage-green mark keeps its brand color
// instead of being flattened by a brightness/invert filter.
const logoUrl = computed(() => (settingsStore.settings.appearance === 'dark' ? logoDark : logoLight))

const navItems = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/decode', label: 'Decoder', icon: MailQuestionMark },
  { to: '/compose', label: 'Compose', icon: PenLine },
  { to: '/study', label: 'Study', icon: BookOpen },
  { to: '/library', label: 'Library', icon: Library },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/login', label: 'Login', icon: LogIn },
]

const route = useRoute()
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))

const menuOpen = ref(false)
watch(
  () => route.path,
  () => {
    menuOpen.value = false
  },
)
</script>

<template>
  <div class="shell">
    <header class="header">
      <div class="header__inner">
        <RouterLink to="/" class="brand">
          <img :src="logoUrl" alt="TheSignalBridge" class="brand__logo" />
        </RouterLink>

        <button
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

        <nav id="primary-nav" class="nav" :class="{ 'nav--open': menuOpen }">
          <RouterLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="nav-item"
            :class="{ 'nav-item--active': isActive(item.to) }"
          >
            <component :is="item.icon" class="nav-item__icon" :size="16" :stroke-width="2" aria-hidden="true" />
            {{ item.label }}
          </RouterLink>
        </nav>
      </div>
    </header>

    <main class="main">
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
  max-width: 1240px;
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
  gap: 4px;
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
  max-width: 1240px;
  margin: 0 auto;
}

@media (max-width: 860px) {
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
  max-width: var(--layout-max, 1100px);
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

.site-footer__link {
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
