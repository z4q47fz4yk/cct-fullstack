/// <reference types="vite-plus/client" />
/// <reference types="vue-router/auto" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}
