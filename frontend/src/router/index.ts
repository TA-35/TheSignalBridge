import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/decode' },
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
  ],
})

export default router
