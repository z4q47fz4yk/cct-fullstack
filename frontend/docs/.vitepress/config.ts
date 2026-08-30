import { defineConfig } from 'vitepress'
import type { DefaultTheme } from 'vitepress/theme'
import { sites } from '../../site.config'

// https://vitepress.dev/reference/site-config
// 通过泛型扩展 themeConfig，允许自定义字段 appBase（供主题组件读取应用入口）
export default defineConfig<DefaultTheme.Config & { appBase?: string }>({
  lang: 'zh-CN',
  title: 'CCT 施工多目标优化系统',
  description: '基于 NSGA-II 的施工成本、工期、碳排放多目标优化软件',
  // 部署在应用域名的 /docs/ 子路径下（L1 同源双构建），所有站内 URL 自动加前缀
  base: sites.docs.base,
  lastUpdated: true,
  cleanUrls: true,
  ignoreDeadLinks: [
    // 应用路径（SPA history 路由），构建时无需校验
    /^\/project\//,
    // 文档站自身路径（带 /docs/ 前缀的）
    /^\/docs\//,
    // 文档中展示的本机地址，构建时无需访问
    /^https?:\/\/localhost/,
  ],
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    // 自定义字段：供主题组件读取应用入口地址（useData().theme.appBase）
    appBase: sites.app.base,
    nav: [
      { text: '首页', link: '/' },
      { text: '开始使用', link: '/guide/intro' },
      { text: '使用指南', link: '/usage/project' },
      { text: '算法原理', link: '/algorithm/modes' },
      { text: '常见问题', link: '/guide/faq' },
    ],

    sidebar: [
      {
        text: '开始使用',
        items: [
          { text: '软件简介', link: '/guide/intro' },
          { text: '快速开始', link: '/guide/quickstart' },
          { text: '核心概念', link: '/guide/concepts' },
          { text: '常见问题', link: '/guide/faq' },
        ],
      },
      {
        text: '使用指南',
        items: [
          { text: '项目管理', link: '/usage/project' },
          { text: '任务管理（工序）', link: '/usage/schedule' },
          { text: '资源管理', link: '/usage/resources' },
          { text: '日报处理', link: '/usage/daily-report' },
          { text: '资源使用录入', link: '/usage/resource-usage' },
          { text: '分析洞察（优化）', link: '/usage/insights' },
          { text: '碳排放分析', link: '/usage/emission' },
          { text: '项目设置', link: '/usage/settings' },
        ],
      },
      {
        text: '算法原理',
        items: [
          { text: '四种施工模式', link: '/algorithm/modes' },
          { text: 'NSGA-II 优化', link: '/algorithm/nsga2' },
          { text: '关键路径法（CPM）', link: '/algorithm/cpm' },
          { text: '成本现值计算', link: '/algorithm/present-value' },
        ],
      },
      {
        text: '数据参考',
        items: [{ text: '数据结构速查', link: '/reference/data-structures' }],
      },
    ],

    outline: {
      label: '本页目录',
      level: [2, 3],
    },

    docFooter: {
      prev: '上一篇',
      next: '下一篇',
    },

    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '菜单',
    darkModeSwitchLabel: '主题',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',
  },
})
