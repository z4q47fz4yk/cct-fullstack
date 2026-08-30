import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import Layout from './Layout.vue'
import AppLink from './AppLink.vue'
import BackToProject from './BackToProject.vue'

/**
 * 自定义主题 —— 在默认主题基础上：
 * 1. Layout 扩展：导航栏加入「打开系统」入口（指向应用，而非文档站内路径）
 * 2. 注册 <AppLink> 组件：Markdown 正文中指向应用路由的链接组件
 * 3. 注册 <BackToProject> 组件：带 projectId 上下文时渲染「回到项目」链接
 */
export default {
  extends: DefaultTheme,
  Layout,
  enhanceApp({ app }) {
    app.component('AppLink', AppLink)
    app.component('BackToProject', BackToProject)
  },
} satisfies Theme
