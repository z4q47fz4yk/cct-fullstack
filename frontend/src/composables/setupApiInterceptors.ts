import { client } from '@/client/client.gen'
import { defaultTitleFor, normalizeHttpError } from '@/utils/error'
import { notifyError } from '@/composables/useToast'

let registered = false

/**
 * 注册全局 API 错误拦截器。
 *
 * 行为：
 * - 任意失败的 HTTP 响应 → 归一化为 ApiError → 自动 `notifyError` 中文 toast
 * - 调用方可在 SDK options 传 `silent: true` 抑制 toast（用于行内表单错误场景）
 * - 归一化后的 ApiError 仍 `throw`，调用方可继续 `catch` 拿 `e.status / e.message` 等
 *
 * 必须在 `app.mount` 之前调用，且仅调用一次（HMR 与测试可重复调用，守卫幂等）。
 */
export function setupApiInterceptors(): void {
  if (registered) return
  registered = true

  client.interceptors.error.use(async (rawError, response, request, opts) => {
    const status = response?.status ?? 0
    const method = (opts.method ?? request.method).toUpperCase()
    const endpoint = opts.url ?? new URL(request.url).pathname

    const apiErr = normalizeHttpError(rawError, status, method, endpoint)

    const silent = (opts as { silent?: boolean }).silent === true
    if (!silent) {
      notifyError({
        title: defaultTitleFor(status, method, endpoint),
        description: apiErr.message,
      })
    }

    // 会话失效（受保护业务接口 401）：整页跳转登录页并保留回跳目标。
    // /auth/ 端点与静默请求不触发（登录页自身的探测请求不得循环跳转）。
    if (
      status === 401 &&
      !silent &&
      !endpoint.startsWith('/auth/') &&
      !window.location.pathname.startsWith('/login')
    ) {
      const redirect = encodeURIComponent(window.location.pathname + window.location.search)
      window.location.assign(`/login?redirect=${redirect}`)
    }

    return apiErr
  })
}
