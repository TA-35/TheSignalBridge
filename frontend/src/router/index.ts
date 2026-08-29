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
  ],
})

export default router
