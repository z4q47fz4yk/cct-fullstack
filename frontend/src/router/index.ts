import { createRouter, createWebHistory } from 'vue-router'
import { routes, handleHotUpdate } from 'vue-router/auto-routes'

import { ensureAuth, signInAvailable } from '@/composables/useAuth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// 项目存在性校验由各子页面自行处理（404 错误态），
// 此处仅同步拦截非法 projectId，避免阻塞导航的网络请求
router.beforeEach(async (to) => {
  const rawId = (to.params as { projectId?: string }).projectId
  if (rawId) {
    const id = Number(rawId)
    if (Number.isNaN(id)) return { path: '/' }
  }

  // OIDC 登录门槛：已配置第三方登录且未登录时，跳转登录页并保留回跳目标。
  // 未配置 Provider（如纯开发环境）时保持开放访问，不阻塞现有使用方式。
  if (to.path !== '/login') {
    const authed = await ensureAuth()
    if (!authed && (await signInAvailable())) {
      return {
        path: '/login',
        query: to.path === '/' ? undefined : { redirect: to.fullPath },
      }
    }
  }
})

if (import.meta.hot) handleHotUpdate(router)

export default router
