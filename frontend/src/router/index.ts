import { createRouter, createWebHistory } from 'vue-router'
import { routes, handleHotUpdate } from 'vue-router/auto-routes'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// 项目存在性校验由各子页面自行处理（404 错误态），
// 此处仅同步拦截非法 projectId，避免阻塞导航的网络请求
router.beforeEach((to) => {
  const rawId = (to.params as { projectId?: string }).projectId
  if (!rawId) return

  const id = Number(rawId)
  if (Number.isNaN(id)) return { path: '/' }
})

if (import.meta.hot) handleHotUpdate(router)

export default router
