<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const navItems = [
  { to: '/', label: 'Home' },
  { to: '/decode', label: 'Review' },
  { to: '/study', label: 'Study' },
  { to: '/library', label: 'Library' },
  { to: '/settings', label: 'Settings' },
]

const route = useRoute()
const isActive = (to: string) => computed(() => (to === '/' ? route.path === '/' : route.path.startsWith(to)))
</script>

<template>
  <div class="shell">
    <div class="topbar">
      <span class="brand">TheSignalBridge</span>
    </div>

    <div class="frame">
      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ 'nav-item--active': isActive(item.to).value }"
        >
          <span class="nav-dot" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <main class="main">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 18px 18px 48px;
}

.topbar {
  width: 100%;
  max-width: 1240px;
  display: flex;
  align-items: center;
  padding: 0 4px;
}

.brand {
  font-family: var(--font-serif);
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.frame {
  width: 100%;
  max-width: 1240px;
  display: flex;
  background: var(--color-frame);
  border: 1px solid var(--color-border-soft);
  border-radius: 16px;
  overflow: hidden;
  min-height: 760px;
  box-shadow: 0 1px 2px rgba(58, 55, 51, 0.04);
}

.nav {
  width: 236px;
  flex: 0 0 236px;
  border-right: 1px solid var(--color-border-soft);
  background: var(--color-surface-soft);
  padding: 26px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 9px;
  font-size: 14.5px;
  font-weight: 400;
  color: var(--color-text-muted);
  flex-shrink: 0;
  white-space: nowrap;
}

.nav-item--active {
  font-weight: 600;
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
}

.nav-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  border-radius: 999px;
  background: var(--color-border-strong);
}

.nav-item--active .nav-dot {
  background: var(--color-primary);
}

.main {
  flex: 1;
  min-width: 0;
  padding: 32px 36px 40px;
}

@media (max-width: 720px) {
  .frame {
    flex-direction: column;
    min-height: 0;
  }

  .nav {
    width: 100%;
    flex: 0 0 auto;
    flex-direction: row;
    border-right: none;
    border-bottom: 1px solid var(--color-border-soft);
    padding: 10px 12px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }

  .nav::-webkit-scrollbar {
    display: none;
  }

  .main {
    padding: 22px 18px 28px;
  }
}
</style>
