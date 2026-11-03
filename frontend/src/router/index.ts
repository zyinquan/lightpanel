import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '概览' },
  },
  {
    path: '/catalog',
    name: 'catalog',
    component: () => import('@/views/CatalogView.vue'),
    meta: { title: '软件' },
  },
  {
    path: '/containers',
    name: 'containers',
    component: () => import('@/views/ContainersView.vue'),
    meta: { title: '容器' },
  },
  {
    path: '/stacks',
    name: 'stacks',
    component: () => import('@/views/StacksView.vue'),
    meta: { title: '编排' },
  },
  {
    path: '/commands',
    name: 'commands',
    component: () => import('@/views/CommandsView.vue'),
    meta: { title: '命令' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '设置' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  const title = (to.meta.title as string | undefined) ?? ''
  document.title = title ? `${title} · LightPanel` : 'LightPanel'
})

export default router
