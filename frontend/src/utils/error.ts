/**
 * 归一化后的 API 错误。
 * - `status === 0` 表示网络层错误（fetch 阶段，未进入 HTTP 协议）
 * - `isValidation === true` 表示 422 校验错误
 * - `detail` 保留后端原始 detail 字段（数组或字符串），供调用方进一步处理
 */
export class ApiError extends Error {
  override readonly name = 'ApiError'

  constructor(
    message: string,
    public readonly status: number,
    public readonly detail: unknown,
    public readonly endpoint: string,
    public readonly method: string,
    public readonly isValidation: boolean,
    public readonly isNetwork: boolean,
  ) {
    super(message)
  }
}

/**
 * 将拦截器捕获的原始错误（已 parse 的 body 或字符串）归一化为 ApiError。
 * 优先级：网络异常 > 422 数组 detail > 字符串 detail > HTTP 状态码兜底。
 */
export function normalizeHttpError(
  raw: unknown,
  status: number,
  method: string,
  endpoint: string,
): ApiError {
  if (status === 0) {
    return new ApiError('网络异常，请检查连接后重试', 0, raw, endpoint, method, false, true)
  }

  if (status === 422 && raw && typeof raw === 'object') {
    const detail = (raw as { detail?: unknown }).detail
    if (Array.isArray(detail) && detail.length > 0) {
      const msgs = detail
        .map((d) =>
          d && typeof d === 'object' && 'msg' in d ? (d as { msg?: unknown }).msg : undefined,
        )
        .filter((m): m is string => typeof m === 'string' && m.length > 0)
      if (msgs.length > 0) {
        return new ApiError(msgs.join('；'), status, detail, endpoint, method, true, false)
      }
    }
  }

  if (raw && typeof raw === 'object') {
    const detail = (raw as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail.length > 0) {
      return new ApiError(detail, status, detail, endpoint, method, status === 422, false)
    }
  }

  return new ApiError(
    `操作失败（HTTP ${status}）`,
    status,
    raw,
    endpoint,
    method,
    status === 422,
    false,
  )
}

interface TitleRule {
  re: RegExp
  title: string
}

const TITLE_RULES: TitleRule[] = [
  { re: /^POST \/optimize-record/, title: '启动优化失败' },
  { re: /^DELETE \/optimize-record\//, title: '停止优化失败' },
  { re: /^POST \/task(\/|$|\?)/, title: '创建任务失败' },
  { re: /^PUT \/task\//, title: '更新任务失败' },
  { re: /^DELETE \/task\//, title: '删除任务失败' },
  { re: /^POST \/resource.*import/, title: '导入资源失败' },
  { re: /^POST \/resource(\/|$|\?)/, title: '创建资源失败' },
  { re: /^POST \/project(\/|$|\?)/, title: '创建项目失败' },
  { re: /^PUT \/project\//, title: '更新项目失败' },
  { re: /^DELETE \/project\//, title: '删除项目失败' },
]

/**
 * 根据 HTTP 状态码与端点生成 toast 标题。
 * 优先级：状态码语义化 > 启发式 (method + endpoint) 映射 > 「操作失败」兜底
 */
export function defaultTitleFor(status: number, method: string, endpoint: string): string {
  if (status === 422) return '提交内容有误'
  if (status === 401) return '请先登录'
  if (status === 403) return '没有权限'
  if (status === 404) return '资源不存在'
  if (status === 409) return '操作冲突'
  if (status === 0) return '网络异常'
  if (status >= 500) return '服务器异常'

  const key = `${method} ${endpoint}`
  return TITLE_RULES.find((r) => r.re.test(key))?.title ?? '操作失败'
}

/**
 * 将任意错误（HTTP 校验错误、ApiError、JS Error、unknown）格式化为面向用户的中文提示。
 *
 * 优先级：
 * 1. `ApiError.message`（拦截器归一化后的友好文本）
 * 2. FastAPI `HttpValidationError.detail[].msg`，以「；」拼接
 * 3. FastAPI `ErrorResponse.detail`（字符串 detail）
 * 4. `Error.message`
 * 5. `fallback`
 */
export function formatHttpError(err: unknown, fallback = '操作失败，请重试'): string {
  if (err instanceof ApiError) return err.message || fallback

  if (err && typeof err === 'object' && 'detail' in err) {
    const detail = (err as { detail: unknown }).detail

    if (Array.isArray(detail) && detail.length > 0) {
      const msgs = detail
        .map((d) =>
          d && typeof d === 'object' && 'msg' in d ? (d as { msg?: unknown }).msg : undefined,
        )
        .filter((m): m is string => typeof m === 'string' && m.length > 0)
      if (msgs.length > 0) return msgs.join('；')
    }

    if (typeof detail === 'string' && detail.length > 0) return detail
  }

  if (err instanceof Error && err.message) return err.message
  return fallback
}
