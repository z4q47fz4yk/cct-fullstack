/**
 * 认证状态（模块级单例，路由守卫 / 登录页 / 用户菜单共用）。
 *
 * - `ensureAuth()`：惰性拉取一次 `/auth/me` 并缓存结果（静默，不弹 toast）；
 * - `signInAvailable()`：`/auth/providers` 非空即认为系统配置了第三方登录，
 *   路由守卫据此决定是否强制跳转登录页（未配置 Provider 时保持开放访问）；
 * - `logout()`：调用后端清除会话 Cookie 后整页跳转登录页（全量重载保证状态归零）。
 */
import { computed, ref, type ComputedRef } from 'vue'

import { Auth } from '@/client/sdk.gen'
import type { MeResp, ProviderInfo } from '@/client/types.gen'

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
