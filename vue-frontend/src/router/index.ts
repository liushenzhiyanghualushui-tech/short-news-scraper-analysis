import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/Dashboard.vue')
    },
    {
      path: '/news',
      name: 'news',
      component: () => import('@/views/NewsList.vue')
    },
    {
      path: '/scrapers',
      name: 'scrapers',
      component: () => import('@/views/Scrapers.vue')
    },
    {
      path: '/logs',
      name: 'logs',
      component: () => import('@/views/Logs.vue')
    }
  ]
})

export default router
