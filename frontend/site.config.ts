/**
 * 站点共享配置 —— 应用（/）与文档站（/docs/）唯一的路径事实来源。
 *
 * 两端构建共同 import 本文件，所有跨站路径只在此处定义一次：
 * - 应用侧：docsHref() 生成指向文档站的链接（导航、按钮）
 * - 文档侧：sites.docs.base 作为 VitePress base；AppLink 组件用 appHref() 生成指向应用的链接
 *
 * 注意：
 * - 不要在此硬编码域名，origin 留空表示同源部署；
 * - 文档站导航/侧边栏中不要直接写应用路径（会被 VitePress withBase 加 /docs/ 前缀），
 *   一律使用 <AppLink> 组件或带 target 的原生 <a>。
 */

export const sites = {
  app: {
    base: '/',
    origin: '', // 同源部署；跨域部署时填 https://app.example.com
  },
  docs: {
    base: '/docs/',
    origin: '', // 同源部署；跨域部署时填 https://docs.example.com
  },
} as const

/** 生成文档站内链接：docsHref('/guide/intro') → '/docs/guide/intro' */
export const docsHref = (path: string) =>
  `${sites.docs.origin}${sites.docs.base}${path.replace(/^\//, '')}`

/** 生成应用内链接：appHref('/project/1') → '/project/1' */
export const appHref = (path: string) =>
  `${sites.app.origin}${sites.app.base}${path.replace(/^\//, '')}`
