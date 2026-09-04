import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { routes, handleHotUpdate } from 'vue-router/auto-routes'

import { ensureAuth, signInAvailable } from '@/composables/useAuth'
import {
  CAPABILITY_ROUTE_NAMES,
  loadCapabilities,
  useCapabilities,
} from '@/composables/useCapabilities'

/**
 * "能力门控"路由名集合：这些路由会在 auto-routes 中**默认存在**，
 * 但需要按后端 /health 探测结果动态决定是否注册。
 *
 * 在这里从 auto-routes 默认 routes 里剔除它们，避免：
 * - auto-routes 注册了 /login，但后端未启用登录 → 用户可见但点击后空白；
 * - auto-routes 注册了 /project/[projectId]/daily-report/ai，但后端未启用 AI →
 *   用户通过 URL 直访可用，但导入页的"AI 生成配置"按钮跳过去是空页面。
 *
 * 这些路由会由 setupRouter() 按后端能力结果**重新**注册。
 */
const GATED_ROUTE_NAMES = new Set<string>([
  CAPABILITY_ROUTE_NAMES.login,
  CAPABILITY_ROUTE_NAMES.aiConfig,
])

// 过滤掉能力门控路由：剩下的就是"无论后端如何配置都会展示"的核心路由
const coreRoutes: RouteRecordRaw[] = routes.filter(
  (r) => !(typeof r.name === 'string' && GATED_ROUTE_NAMES.has(r.name)),
)

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: coreRoutes,
})

/**
 * 一次性挂载与"后端能力"绑定的动态路由：
 * - 在能力探测**完成**之前不挂载任何门控路由（flags 一律按 false 处理，
 *   见 useCapabilities），避免在 AI/登录未配置的部署中误暴露入口；
 * - 探测完成后按 authEnabled / aiEnabled 注册相应路由；
 * - 若当前正停留在将被移除的路由，跳转到首页避免用户卡在 404。
 *
 * 该函数应只调用一次（在 main.ts 中启动前 await）。
 */
export async function setupRouter(): Promise<void> {
  await loadCapabilities()
  const { authEnabled, aiEnabled } = useCapabilities()

  if (authEnabled.value) {
    // 登录功能已启用 → 注册 /login。
    // 之前已被从 coreRoutes 剔除，这里 addRoute 一次即可。
    router.addRoute({
      path: '/login',
      name: CAPABILITY_ROUTE_NAMES.login,
      component: () => import('@/pages/login.vue'),
      meta: { title: '登录' },
    })
  }

  if (aiEnabled.value) {
    // AI 功能已启用 → 注册 AI 配置生成页。
    // 该路由是 project 子路由，父级 /project/:projectId/daily-report 已在
    // coreRoutes 中存在，addRoute 会按 path 把它挂到对应的父级下。
    router.addRoute({
      path: '/project/:projectId/daily-report/ai',
      name: CAPABILITY_ROUTE_NAMES.aiConfig,
      component: () => import('@/pages/project/[projectId]/daily-report/ai.vue'),
      meta: {
        title: 'AI 生成解析配置',
        icon: 'auto_awesome',
        // 从侧边栏隐藏：AI 配置生成是「导入日报」向导的前置步骤，
        // 从导入日报页的引导卡片进入
        showInNav: false,
        parentName: '/project/[projectId]/daily-report',
        navOrder: 0,
      },
    })
  }

  // 404 兜底：catch-all 路由（pathMatchParam 必须含 '*'，path 用 :pathMatch(.*)*）。
  // 注意：必须**最后**注册，否则会过早匹配。
  router.addRoute({
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/pages/not-found.vue'),
    meta: { title: '页面未找到' },
  })

  // 如果当前正在一条"刚被剔除"的路由上，跳到首页避免卡在 404
  redirectOrphanRoute(authEnabled.value, aiEnabled.value)
}

/**
 * 探测完成后做一次校正：如果当前停留在一条不再被注册的路由上，
 * 跳转首页（用户也可能刷新到该路由，下一次导航也会重定向到 404）。
 */
function redirectOrphanRoute(authEnabled: boolean, aiEnabled: boolean): void {
  const current = router.currentRoute.value
  const orphan =
    (current.name === CAPABILITY_ROUTE_NAMES.login && !authEnabled) ||
    (current.name === CAPABILITY_ROUTE_NAMES.aiConfig && !aiEnabled)
  if (orphan) {
    void router.replace('/')
  }
}

// 项目存在性校验由各子页面自行处理（404 错误态），
// 此处仅同步拦截非法 projectId，避免阻塞导航的网络请求
router.beforeEach(async (to) => {
  const rawId = (to.params as { projectId?: string }).projectId
  if (rawId) {
    const id = Number(rawId)
    if (Number.isNaN(id)) return { path: '/' }
  }

  // 守卫兜底：万一 setupRouter 之前未完成探测，确保至少探测过
  // （典型场景是用户直刷新进入，main.ts 已 await setupRouter，此分支几乎不会触发）
  const { authEnabled, aiEnabled } = useCapabilities()
  await loadCapabilities()

  // 能力门控：未启用的功能对应的路由不允许进入 → 走 404
  if (to.name === CAPABILITY_ROUTE_NAMES.aiConfig && !aiEnabled.value) {
    return { path: '/_not_found_' }
  }
  if (to.name === CAPABILITY_ROUTE_NAMES.login && !authEnabled.value) {
    return { path: '/_not_found_' }
  }

  // OIDC 登录门槛：已配置第三方登录且未登录时，跳转登录页并保留回跳目标。
  // 未配置 Provider（如纯开发环境）时保持开放访问，不阻塞现有使用方式。
  //
  // 短路说明：ensureAuth/signInAvailable 内部已先 await loadCapabilities()，
  // 后端未启用登录（authEnabled=false）时不会再发 /api/auth/me 与
  // /api/auth/providers 请求，直接返回 false，避免无意义的探测。
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
