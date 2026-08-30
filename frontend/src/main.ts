import './assets/base.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import * as v from 'valibot'
import '@valibot/i18n/zh-CN'

v.setGlobalConfig({ lang: 'zh-CN' })

import { PiniaColada } from '@pinia/colada'
import { PiniaColadaAutoRefetch } from '@pinia/colada-plugin-auto-refetch'

import App from './App.vue'
import router from './router'
import { setupApiInterceptors } from '@/composables/setupApiInterceptors'
import { useTheme } from '@/composables/useTheme'

// 初始化主题 — 模块级 watcher 在挂载前设置 data-theme，避免 FOUC
useTheme()

const app = createApp(App)
app.use(createPinia())
app.use(PiniaColada, {
  plugins: [PiniaColadaAutoRefetch({ autoRefetch: false })],
})
app.use(router)

setupApiInterceptors()

app.mount('#app')
