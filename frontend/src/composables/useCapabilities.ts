/**
 * 后端能力探测（模块级单例）。
 *
 * 应用启动时**调用且仅调用一次** `/health` 端点，缓存响应结果：
 * - ``auth_enabled``：是否启用了登录功能；
 * - ``ai_enabled``：是否启用了 AI 对话。
 *
 * 未拿到响应前，标志位一律按 `false` 处理（保守默认）：
 * - 避免在用户尚未登录的部署中误展示 AI 入口；
 * - 避免在 AI 未配置的部署中误展示登录入口（即"系统已配置了第三方登录"的暗示）。
 *
 * 路由守卫、动态路由注册都依赖这里的标志位。
 */
import { computed, ref, type ComputedRef } from 'vue'

export interface Capabilities {
  /** 登录功能是否启用（OIDC Provider 已配置） */
  authEnabled: ComputedRef<boolean>
  /** AI 对话是否启用（PI_ENABLED） */
  aiEnabled: ComputedRef<boolean>
  /** 是否已拿到后端响应（false 表示仍处于"能力未知"状态） */
  loaded: ComputedRef<boolean>
}

const authEnabled = ref(false)
const aiEnabled = ref(false)
const loaded = ref(false)
let loadingPromise: Promise<void> | null = null

/**
 * 触发一次 `/health` 请求（幂等，并发安全）。
 *
 * 调用方应在应用启动时尽早调用一次；后续重复调用立即返回已完成的 Promise。
 */
export function loadCapabilities(): Promise<void> {
  if (loaded.value) return Promise.resolve()
  if (loadingPromise) return loadingPromise

  loadingPromise = (async () => {
    try {
      // 直接用底层 fetch：避免在 Pinia Colada 启动之前强依赖其上下文，
      // 且只需调用一次，无缓存需求。
      const res = await fetch('/api/health')
      if (!res.ok) {
        // 后端不可用 / 5xx：保持 false，进入能力未知状态
        return
      }
      const body = (await res.json()) as { auth_enabled?: boolean; ai_enabled?: boolean }
      authEnabled.value = Boolean(body.auth_enabled)
      aiEnabled.value = Boolean(body.ai_enabled)
    } catch {
      // 网络异常同样保持 false（与 useAuth 中 providers 的处理一致）
    } finally {
      loaded.value = true
    }
  })()
  return loadingPromise
}

/**
 * 获取能力状态（响应式）。
 *
 * 返回的 flags 在首次 fetch 完成前一律为 false（保守默认）。
 */
export function useCapabilities(): Capabilities {
  // 在被调用时立即确保已经触发探测（幂等）
  void loadCapabilities()
  return {
    authEnabled: computed(() => authEnabled.value),
    aiEnabled: computed(() => aiEnabled.value),
    loaded: computed(() => loaded.value),
  }
}

/**
 * 纯函数：在路由列表中加入 / 移除登录、AI 相关路由。
 *
 * 这是 vue-router 动态路由的标准用法之一（"删除路由"）：
 * - ``addRoute`` 添加具名路由；
 * - ``removeRoute`` 通过 name 删除；
 *
 * 调用方负责：识别当前路由是否对应登录/AI 功能，再决定是否注册。
 *
 * 名称与 ``vue-router/auto-routes`` 生成的 ``typed-router.d.ts`` 中的
 * ``RouteNamedMap`` 保持一致（路由名 = 文件相对 src/pages 的路径）。
 */
export const CAPABILITY_ROUTE_NAMES = {
  login: '/login',
  aiConfig: '/project/[projectId]/daily-report/ai',
} as const
