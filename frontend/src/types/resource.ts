/**
 * Resource type definitions
 * 资源类型定义
 */
import type { ResourceResp, ResourceCategory, ResourceCreate } from '@/client/types.gen'

// 直接使用后端生成的类型
export type { ResourceResp as Resource, ResourceCategory }

// 分类配置项
export interface CategoryConfig {
  label: string
  icon: string
  statLabel: string
}

// 分类配置映射
export const categoryConfigMap: Record<ResourceCategory, CategoryConfig> = {
  labor: {
    label: '人工',
    icon: 'engineering',
    statLabel: '劳务单元总数',
  },
  machinery: {
    label: '机械',
    icon: 'construction',
    statLabel: '机械单元总数',
  },
  transport: {
    label: '运输',
    icon: 'local_shipping',
    statLabel: '运输单元总数',
  },
  material: {
    label: '材料',
    icon: 'inventory_2',
    statLabel: '材料类型总数',
  },
  others: {
    label: '其他',
    icon: 'more_horiz',
    statLabel: '其他类型总数',
  },
}

// 分类颜色已迁移至 themeColors.getCategoryColor()（主题驱动，随主题切换）。
// 类别色与语义色分离：蓝=人工、琥珀=机械、青=材料、紫=运输、灰=其他。

// ── 新增/编辑资源弹窗扩展（限制 / 周转复用） ─────────────────────────

/** 资源限制草稿：enabled=false 表示弹窗内不创建（或提交时删除既有限制） */
export interface ConstraintDraft {
  enabled: boolean
  maxUsage: number | null
  description: string
}

/** 周转复用草稿（仅 material 分类有意义） */
export interface ReuseDraft {
  enabled: boolean
  maxReuses: number
  reuseCount: number
  affectCost: boolean
  description: string | null
}

/** 新增/编辑资源弹窗提交载荷（资源基础 + 限制/复用子对象） */
export interface ResourceFormPayload {
  resource: ResourceCreate
  constraint: ConstraintDraft
  reuse: ReuseDraft
}
