/**
 * 认证状态（模块级单例，路由守卫 / 登录页 / 用户菜单共用）。
 *
 * - `ensureAuth()`：惰性拉取一次 `/auth/me` 并缓存结果（静默，不弹 toast）；
 * - `signInAvailable()`：`/auth/providers` 非空即认为系统配置了第三方登录，
 *   路由守卫据此决定是否强制跳转登录页（未配置 Provider 时保持开放访问）；
 * - `logout()`：调用后端清除会话 Cookie 后整页跳转登录页（全量重载保证状态归零）。
 *
 * 能力短路：当 `useCapabilities` 探测完成且 `auth_enabled=false` 时，
 * `ensureAuth` 与 `signInAvailable` 不再向后端发送任何 `/auth/*` 请求——
 * `/api/auth/me` 与 `/api/auth/providers` 都是登录功能的探测，
 * 未启用登录时调用它们毫无意义、徒增噪声。`UserMenu` 也会因 `me === null`
 * 自动隐藏（`v-if="me"`），符合"未启用登录则不显示账户菜单"语义。
 */
import { computed, ref, type ComputedRef } from 'vue'

import { Auth } from '@/client/sdk.gen'
import type { MeResp, ProviderInfo } from '@/client/types.gen'
import { loadCapabilities, useCapabilities } from '@/composables/useCapabilities'

const me = ref<MeResp | null>(null)
let meInitialized = false
let meLoading: Promise<boolean> | null = null

let providersCache: ProviderInfo[] | null = null

/** 当前登录用户（响应式；未登录为 null） */
export function useAuthUser(): ComputedRef<MeResp | null> {
  return computed(() => me.value)
}

/** 确保认证状态已加载（幂等，可并发调用）；返回是否已登录。 */
export async function ensureAuth(): Promise<boolean> {
  // 探测后端能力：未启用登录时跳过 /auth/me，避免无意义的请求
  await loadCapabilities()
  const { authEnabled } = useCapabilities()
  if (!authEnabled.value) {
    // 标记"已初始化"，让后续调用走缓存分支而不再发起探测
    me.value = null
    meInitialized = true
    meLoading = null
    return false
  }

  if (meLoading) return meLoading
  if (meInitialized) return me.value !== null

  meLoading = (async () => {
    meInitialized = true
    try {
      const { data } = await Auth.getAuthMe({ silent: true })
      me.value = data ?? null
    } catch {
      me.value = null
    } finally {
      meLoading = null
    }
    return me.value !== null
  })()
  return meLoading
}

/** 系统是否配置了可登录的第三方 Provider。 */
export async function signInAvailable(): Promise<boolean> {
  // 探测后端能力：未启用登录时跳过 /auth/providers，避免无意义的请求
  await loadCapabilities()
  const { authEnabled } = useCapabilities()
  if (!authEnabled.value) {
    // 缓存"已探测且为空"，让后续调用直接走缓存分支
    providersCache = []
    return false
  }

  if (providersCache !== null) return providersCache.length > 0
  try {
    const { data } = await Auth.listAuthProviders({ silent: true })
    providersCache = data ?? []
  } catch {
    // 网络异常按“未配置”处理：不因登录探测失败而锁死站点访问
    providersCache = []
  }
  return providersCache.length > 0
}

/** 退出登录：清除后端会话 Cookie 并整页跳转登录页。 */
export async function logout(): Promise<void> {
  try {
    await Auth.logout({ silent: true })
  } catch {
    // 登出请求失败也照常跳转：重载后 /auth/me 会重新判定会话状态
  }
  me.value = null
  meInitialized = false
  window.location.assign('/login')
}
