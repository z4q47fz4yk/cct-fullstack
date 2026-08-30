import type { TaskResp } from '@/client/types.gen'

/**
 * 计算工序的起始天数（基于前置工序的 FS 逻辑）
 * 从 schedule.vue 提取，逻辑不变
 */
export function calculateStartDay(task: TaskResp, taskMap: Map<number, TaskResp>): number {
  if (!task.predecessors || task.predecessors.length === 0) return 0

  let maxEndDay = 0
  for (const pred of task.predecessors) {
    const predTask = taskMap.get(pred.id)
    if (predTask) {
      const predStartDay = calculateStartDay(predTask, taskMap)
      const predEndDay = predStartDay + predTask.duration
      maxEndDay = Math.max(maxEndDay, predEndDay)
    }
  }
  return maxEndDay
}

/**
 * 按拓扑依赖关系排序工序，用于甘特图从上到下的显示顺序
 *
 * 算法：
 * 1. 找连通分量（无向图 DFS）
 * 2. 每个分量内做有向 DFS 拓扑排序（后序反转）
 * 3. 分量间按根节点 (startDay, id) 排序
 *
 * 保证：
 * - 连通分量内的工序聚在一起（不会交叉）
 * - 前置工序总在后继工序之上
 * - DFS 遍历后继时按 (startDay, id) 排序，确保结果确定性
 */
export function sortTasksForGantt<T extends TaskResp>(tasks: T[]): T[] {
  if (tasks.length === 0) return []

  // 1. 构建 taskMap 和 startDay 映射
  const taskMap = new Map<number, T>()
  const startDayMap = new Map<number, number>()
  for (const t of tasks) {
    taskMap.set(t.id, t)
    startDayMap.set(t.id, calculateStartDay(t, taskMap))
  }

  // 2. 构建后继图（从 predecessors 反向推导）
  const successors = new Map<number, number[]>()
  for (const t of tasks) {
    successors.set(t.id, [])
  }
  for (const t of tasks) {
    for (const pred of t.predecessors ?? []) {
      const succs = successors.get(pred.id)
      if (succs) succs.push(t.id)
    }
  }

  // 3. 找连通分量（无向图 DFS）
  const adj = new Map<number, number[]>()
  for (const t of tasks) {
    adj.set(t.id, [])
  }
  for (const t of tasks) {
    for (const pred of t.predecessors ?? []) {
      adj.get(t.id)?.push(pred.id)
      adj.get(pred.id)?.push(t.id)
    }
  }

  const visited = new Set<number>()
  const components: number[][] = []

  const dfsComponent = (id: number, comp: number[]) => {
    visited.add(id)
    comp.push(id)
    for (const neighbor of adj.get(id) ?? []) {
      if (!visited.has(neighbor)) {
        dfsComponent(neighbor, comp)
      }
    }
  }

  // 按从小 id 开始 DFS，保证分量发现顺序确定性
  const sortedIds = Array.from(taskMap.keys()).sort((a, b) => a - b)
  for (const id of sortedIds) {
    if (!visited.has(id)) {
      const comp: number[] = []
      dfsComponent(id, comp)
      components.push(comp)
    }
  }

  // 4. 每个分量内做有向 DFS 拓扑排序
  const result: T[] = []
  // 分量间排序键：分量中根节点（无前置的节点）的最小 (startDay, id)
  const componentSortKeys = components.map((comp) => {
    const roots = comp.filter((id) => {
      const t = taskMap.get(id)!
      return !t.predecessors || t.predecessors.length === 0
    })
    // 如果没有根节点（所有节点都有前置，理论上不会发生），用分量中最小 id
    const keys =
      roots.length > 0
        ? roots.map((id) => [startDayMap.get(id) ?? 0, id] as [number, number])
        : [[0, Math.min(...comp)] as [number, number]]
    const minKey = keys.reduce((best, cur) =>
      cur[0] < best[0] || (cur[0] === best[0] && cur[1] < best[1]) ? cur : best,
    )
    return { comp, sortKey: minKey }
  })

  componentSortKeys.sort((a, b) => {
    if (a.sortKey[0] !== b.sortKey[0]) return a.sortKey[0] - b.sortKey[0]
    return a.sortKey[1] - b.sortKey[1]
  })

  for (const { comp } of componentSortKeys) {
    // 找分量中的根节点
    const roots = comp.filter((id) => {
      const t = taskMap.get(id)!
      return !t.predecessors || t.predecessors.length === 0
    })
    // 根节点按 (startDay, id) 排序
    roots.sort((a, b) => {
      const sa = startDayMap.get(a) ?? 0
      const sb = startDayMap.get(b) ?? 0
      if (sa !== sb) return sa - sb
      return a - b
    })

    // DFS 拓扑排序：后序反转
    const topoOrder: number[] = []
    const dfsVisited = new Set<number>()

    const dfsTopo = (id: number) => {
      if (dfsVisited.has(id)) return
      dfsVisited.add(id)
      // 后继按 (startDay, id) 升序遍历，确保 DFS 深入顺序确定性
      const succIds = (successors.get(id) ?? [])
        .filter((s) => comp.includes(s))
        .sort((a, b) => {
          const sa = startDayMap.get(a) ?? 0
          const sb = startDayMap.get(b) ?? 0
          if (sa !== sb) return sa - sb
          return a - b
        })
      for (const s of succIds) {
        dfsTopo(s)
      }
      topoOrder.push(id)
    }

    // 从每个根节点开始 DFS
    for (const rootId of roots) {
      dfsTopo(rootId)
    }
    // 处理分量中没有根的节点（理论上不应出现）
    for (const id of comp) {
      if (!dfsVisited.has(id)) {
        dfsTopo(id)
      }
    }

    // 后序反转 → 前置在前
    const reversed = topoOrder.reverse()
    for (const id of reversed) {
      result.push(taskMap.get(id)!)
    }
  }

  return result
}
