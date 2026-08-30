import { computed } from 'vue'
import { useQuery } from '@pinia/colada'
import { useRouter, type RouteLocationRaw } from 'vue-router'
import { useProjectContext } from '@/composables/useProjectContext'
import { PROJECT_QUERY_STALE_MS } from '@/composables/useProjectApi'
import { getProjectQuery } from '@/client/@pinia/colada.gen'

export interface NavItemChild {
  /** 路由 name，用于激活判断 */
  name: string
  /** 导航目标（具名路由 location 对象），直接传给 RouterLink */
  to: RouteLocationRaw
  label: string
  icon: string
}

export interface NavGroup {
  /** 分组标题（如「计划阶段」）；空字符串表示无标题分组 */
  label: string
  children: NavItemChild[]
}

export interface NavItem {
  /** 路由 name，用于激活判断 */
  name: string
  /** 父项点击时跳转的目标（默认是首个子项的 to，或自身） */
  to: RouteLocationRaw
  icon: string
  label: string
  projectScoped: boolean
  children?: NavItemChild[]
  /** 阶段分组（子菜单含 meta.group 时生成，优先于扁平 children 渲染） */
  groups?: NavGroup[]
}

/** 阶段分组的固定展示顺序（项目生命周期），未列出的组保持首次出现顺序 */
const STAGE_ORDER = ['计划阶段', '施工阶段', '评价阶段']

export function useSidebarNav() {
  const router = useRouter()
  const { currentProjectId, isInProject } = useProjectContext()

  /**
   * 构建具名路由 location 对象。
   * 若为项目级路由且当前在项目内，注入 projectId 参数。
   */
  const buildTo = (name: string, projectScoped: boolean): RouteLocationRaw => {
    if (projectScoped && currentProjectId.value !== null) {
      return { name, params: { projectId: currentProjectId.value } } as RouteLocationRaw
    }
    return { name } as RouteLocationRaw
  }

  const navItems = computed<NavItem[]>(() => {
    const routes = router.getRoutes()

    // 1. 收集所有 showInNav 的路由
    const allNavRoutes = routes.filter((r) => r.meta?.showInNav)

    // 2. 分离顶级项（无 parentName）和子项（有 parentName）
    const topLevel = allNavRoutes
      .filter((r) => !r.meta.parentName)
      .sort((a, b) => (a.meta.navOrder ?? 99) - (b.meta.navOrder ?? 99))
    const childRoutes = allNavRoutes.filter((r) => r.meta.parentName)

    // 3. 按 parentName 分组
    const childrenByParent = new Map<string, typeof childRoutes>()
    for (const child of childRoutes) {
      const parentName = child.meta.parentName as string
      const group = childrenByParent.get(parentName) ?? []
      group.push(child)
      childrenByParent.set(parentName, group)
    }

    return (
      topLevel
        .map((r) => {
          const itemName = r.name as string
          const projectScoped = r.path.includes(':projectId')

          // 获取该顶级项下的子项，按 navOrder 排序
          const rawChildren = childrenByParent.get(itemName) ?? []
          const sortedChildren = rawChildren.sort(
            (a, b) => (a.meta.navOrder ?? 99) - (b.meta.navOrder ?? 99),
          )
          // 阶段分组：按 meta.group 聚合，组间顺序由 STAGE_ORDER 决定（navOrder 仅决定组内排序）
          const children: NavItemChild[] = []
          const groupMap = new Map<string, NavItemChild[]>()
          for (const c of sortedChildren) {
            const childItem: NavItemChild = {
              name: c.name as string,
              to: buildTo(c.name as string, projectScoped),
              label: c.meta.title,
              icon: c.meta.icon || 'circle',
            }
            children.push(childItem)
            const group = String(c.meta.group ?? '').trim()
            if (!groupMap.has(group)) groupMap.set(group, [])
            groupMap.get(group)!.push(childItem)
          }
          const groups: NavGroup[] = Array.from(groupMap.entries()).map(
            ([label, groupChildren]) => ({
              label,
              children: groupChildren,
            }),
          )
          // 组间顺序按 STAGE_ORDER（计划 → 施工 → 评价），组内保持 navOrder
          groups.sort((a, b) => {
            const ia = STAGE_ORDER.indexOf(a.label)
            const ib = STAGE_ORDER.indexOf(b.label)
            return (ia === -1 ? STAGE_ORDER.length : ia) - (ib === -1 ? STAGE_ORDER.length : ib)
          })

          return {
            name: itemName,
            to: buildTo(r.name as string, projectScoped),
            icon: r.meta.icon || 'circle',
            label: r.meta.title,
            projectScoped,
            children: children.length > 0 ? children : undefined,
            groups: groups.length > 0 ? groups : undefined,
          }
        })
        // 仅在项目上下文中显示项目级导航项
        .filter((item) => !item.projectScoped || isInProject.value)
    )
  })

  // 当前项目名称（用于 SideBar 显示）
  // 通过 getProjectQuery 拿真实名称，加载中显示占位 fallback
  const projectQuery = useQuery(() => ({
    ...getProjectQuery({
      path: { id: currentProjectId.value ?? -1 },
    }),
    enabled: currentProjectId.value !== null,
    staleTime: PROJECT_QUERY_STALE_MS,
  }))

  const currentProjectName = computed(() => {
    if (!isInProject.value) return ''
    const data = projectQuery.state.value?.data as { name?: string } | undefined
    if (data?.name) return data.name
    // 加载中或失败：回退到 id 占位（不再长时间显示"项目 undefined"）
    return `项目 ${currentProjectId.value}`
  })

  const isLoadingProject = computed(() => projectQuery.asyncStatus.value === 'loading')

  return { navItems, currentProjectName, isLoadingProject }
}
