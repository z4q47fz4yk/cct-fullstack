import type { TagNodeResp } from '@/client/types.gen'

/** 展平后的标签树节点：带深度与祖先路径 */
export interface FlattenedTagNode {
  node: TagNodeResp
  depth: number
  /** 祖先链（含自身）的标签名，用于详情页面包屑 */
  path: string[]
}

/** 展平标签树（先序），返回所有节点的扁平列表 */
export function flattenTagTree(tree: TagNodeResp[]): FlattenedTagNode[] {
  const result: FlattenedTagNode[] = []
  function walk(nodes: TagNodeResp[], depth: number, ancestors: string[]) {
    for (const node of nodes) {
      const path = [...ancestors, node.name]
      result.push({ node, depth, path })
      walk(node.children ?? [], depth + 1, path)
    }
  }
  walk(tree, 0, [])
  return result
}

/** 统计节点子树中的标签总数（含自身） */
export function countSubtree(node: TagNodeResp): number {
  const children = node.children ?? []
  return 1 + children.reduce((sum, child) => sum + countSubtree(child), 0)
}

/** 按 id 查找节点 */
export function findTagNode(tree: TagNodeResp[], id: number): TagNodeResp | undefined {
  for (const node of tree) {
    if (node.id === id) return node
    const found = findTagNode(node.children ?? [], id)
    if (found) return found
  }
  return undefined
}

/** 按 id 查找节点及其祖先链（根到自身） */
export function findTagPath(tree: TagNodeResp[], id: number): TagNodeResp[] {
  for (const node of tree) {
    if (node.id === id) return [node]
    const path = findTagPath(node.children ?? [], id)
    if (path.length > 0) return [node, ...path]
  }
  return []
}

/** 收集节点子树内全部标签 id（含自身） */
export function collectSubtreeIds(node: TagNodeResp): number[] {
  return [node.id, ...(node.children ?? []).flatMap(collectSubtreeIds)]
}

/** 收集整棵树全部标签 id */
export function collectAllTagIds(tree: TagNodeResp[]): number[] {
  return tree.flatMap(collectSubtreeIds)
}

/** 按维度分组的标签树（根节点自带 dimensionId） */
export interface TagTreeGroup {
  dimensionId: number
  tree: TagNodeResp[]
}

/** 将多棵根树按 dimensionId 分组（保持首次出现顺序） */
export function groupTagTreesByDimension(trees: TagNodeResp[]): TagTreeGroup[] {
  const groups: TagTreeGroup[] = []
  const index = new Map<number, number>()
  for (const root of trees) {
    let idx = index.get(root.dimensionId)
    if (idx === undefined) {
      idx = groups.length
      index.set(root.dimensionId, idx)
      groups.push({ dimensionId: root.dimensionId, tree: [] })
    }
    groups[idx]!.tree.push(root)
  }
  return groups
}

/** 构建 dimensionId → 维度名的映射（未知维度回退为 "维度 #id"） */
export function dimensionNameMap(dimensions: { id: number; name: string }[]): Map<number, string> {
  const map = new Map<number, string>()
  for (const d of dimensions) map.set(d.id, d.name)
  return map
}

export function dimensionLabel(map: Map<number, string>, dimensionId: number): string {
  return map.get(dimensionId) ?? `维度 #${dimensionId}`
}
