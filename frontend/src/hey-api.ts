import type { CreateClientConfig } from './client/client.gen'

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  // 同源 /api：dev 由 vite 反代到本 worktree 后端（见 vite.config.ts），部署由 nginx /api 反代；
  // 跨机直连场景可把根 .env 的 VITE_API_BASE 改为 http://host:port（配合 CORS_ALLOW_ALL）
  baseUrl: import.meta.env.VITE_API_BASE ?? '/api',
})
