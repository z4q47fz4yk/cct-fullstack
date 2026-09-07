import type { TagResp } from '@/client/types.gen'

/**
 * 扁平标签分组工具：把标签按 group 分组（空 group → "未分组"）。
 * 供打标选择器 / 图表切片选择器 / 标签管理页共用。
 */
export const UNGROUPED_LABEL = '未分组'

export interface TagGroup {
  /** group 原文（空字符串=未分组） */
  group: string
  /** 展示名（空分组显示为「未分组」） */
  label: string
  tags: TagResp[]
}

/** 把扁平标签按 group 分组（保持传入顺序内的稳定：空分组置顶，其余按首见顺序） */
export function groupTags(tags: TagResp[]): TagGroup[] {
  const order: string[] = []
  const map = new Map<string, TagResp[]>()
  for (const t of tags) {
    const key = t.group ?? ''
    if (!map.has(key)) {
      map.set(key, [])
      order.push(key)
    }
    map.get(key)!.push(t)
  }
  order.sort((a, b) => {
    if (a === '') return -1
    if (b === '') return 1
    return a.localeCompare(b, 'zh')
  })
  return order.map((g) => ({
    group: g,
    label: g === '' ? UNGROUPED_LABEL : g,
    tags: map.get(g) ?? [],
  }))
}

/** 把标签扁平列表按 group 归并成 id → name 映射 */
export function tagIdNameMap(tags: TagResp[]): Map<number, string> {
  const map = new Map<number, string>()
  for (const t of tags) map.set(t.id, t.name)
  return map
}

/** 按分组展示名 + 名称排序后的完整标签列表（供搜索/下拉） */
export function sortTags(tags: TagResp[]): TagResp[] {
  return [...tags].sort((a, b) => {
    const ga = (a.group ?? '') === '' ? UNGROUPED_LABEL : a.group
    const gb = (b.group ?? '') === '' ? UNGROUPED_LABEL : b.group
    if (ga !== gb) return ga.localeCompare(gb, 'zh')
    return a.name.localeCompare(b.name, 'zh')
  })
}

/** 过滤标签：名称/分组匹配关键字 */
export function filterTags(tags: TagResp[], q: string): TagResp[] {
  const kw = q.trim().toLowerCase()
  if (!kw) return tags
  return tags.filter(
    (t) =>
      t.name.toLowerCase().includes(kw) ||
      (t.group ?? '').toLowerCase().includes(kw) ||
      t.description.toLowerCase().includes(kw),
  )
}
