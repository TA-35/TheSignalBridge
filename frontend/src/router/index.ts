import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
    },
    {
      path: '/compose',
      name: 'compose',
      component: () => import('@/views/ComposeView.vue')
    },
    {
      path: '/decode',
      name: 'decode',
      component: () => import('@/views/DecodeView.vue'),
    },
    {
      path: '/study',
      name: 'study',
      component: () => import('@/views/StudyView.vue'),
    },
    {
      path: '/study/:id',
      name: 'card-review',
      component: () => import('@/views/CardReviewView.vue'),
    },
    {
      path: '/library',
      name: 'library',
      component: () => import('@/views/LibraryView.vue'),
    },
    {
      path: '/library/:patternId',
      name: 'pattern-preview',
      component: () => import('@/views/CardReviewView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
    },
    {
      path: '/privacy',
      name: 'privacy',
      component: () => import('@/views/PrivacyView.vue'),
    },
    {
      // One page for both sides of an account: signing in or creating one
      // when signed out, and the ID, pairing codes and deletion once signed
      // in. Named for what it is rather than for one of its two states.
      path: '/account',
      name: 'account',
      component: () => import('@/views/AccountView.vue')
    },
    {
      // The header said "Login" for months and people bookmark things.
      path: '/login',
      redirect: '/account',
    },
  ],
})

export default router
