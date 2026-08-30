import type { CreateClientConfig } from './client/client.gen'

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  // 后端地址由 worktree 根 .env 的 VITE_API_BASE 决定（缺省 localhost:8000）
  baseUrl: import.meta.env.VITE_API_BASE ?? 'http://localhost:8000',
})
