/// <reference types="vite-plus/client" />
/// <reference types="vue-router/auto" />

interface ImportMetaEnv {
  /** 后端 API 基址（由 worktree 根 .env 的 VITE_API_BASE 提供，缺省 http://localhost:8000） */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}
