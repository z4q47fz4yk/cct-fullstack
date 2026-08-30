/**
 * 为生成代码的 Config 扩展业务字段。
 * 拦截器在 `opts.silent === true` 时抑制全局 toast，由调用方自行展示（如 formError）。
 *
 * 不修改 `src/client/`，仅通过模块声明合并扩展。
 * 注：Config<T> 用 ClientOptions 作为类型参数约束，不直接 extends，故必须扩 Config 本身。
 */
declare module '@/client/client/types.gen' {
  interface Config<T> {
    /** 静默错误：抑制全局 toast，由调用方自行展示 */
    silent?: boolean
  }
}

export {}
