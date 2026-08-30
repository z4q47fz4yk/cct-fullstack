import 'vue-router'
import type { RouteNamedMap } from 'vue-router/auto-routes'

declare module 'vue-router' {
  interface RouteMeta {
    title: string
    description?: string
    icon?: string
    showInNav?: boolean
    navOrder?: number
    /**
     * 子菜单阶段分组标题（如「计划阶段 / 施工阶段 / 评价阶段」）。
     * 同一父级下按此字段分组展示，顺序按首次出现顺序。
     */
    group?: string
    /**
     * 子页面声明其所属的父级导航路由 name。
     * 指向 vue-router 自动路由生成的 route name（如 '/project/[projectId]/daily-report'）。
     * 该子页会作为子菜单项出现在父级下方。
     */
    parentName?: keyof RouteNamedMap
  }
}
