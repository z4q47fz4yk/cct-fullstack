import './assets/base.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import * as v from 'valibot'
import '@valibot/i18n/zh-CN'

v.setGlobalConfig({ lang: 'zh-CN' })

import { PiniaColada } from '@pinia/colada'
import { PiniaColadaAutoRefetch } from '@pinia/colada-plugin-auto-refetch'

import App from './App.vue'
import router, { setupRouter } from './router'
import { setupApiInterceptors } from '@/composables/setupApiInterceptors'
import { useTheme } from '@/composables/useTheme'

// 初始化主题 — 模块级 watcher 在挂载前设置 data-theme，避免 FOUC
useTheme()

// 在挂载应用前先探测后端能力（/health）并按需注册路由。
// 未拿到响应前不允许导航，否则首次解析可能错过"AI/登录未启用"的判断。
await setupRouter()

const app = createApp(App)
app.use(createPinia())
app.use(PiniaColada, {
  plugins: [PiniaColadaAutoRefetch({ autoRefetch: false })],
})
app.use(router)

setupApiInterceptors()

app.mount('#app')
