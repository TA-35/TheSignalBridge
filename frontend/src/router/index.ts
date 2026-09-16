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
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue')
    },
  ],
})

export default router
