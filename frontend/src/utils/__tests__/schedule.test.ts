import { describe, expect, it } from 'vite-plus/test'
import { calculateStartDay, sortTasksForGantt } from '@/utils/schedule'
import type { TaskWithTagsResp, TaskDependencyInfo } from '@/client/types.gen'

function makeTask(
  id: number,
  name: string,
  duration: number,
  predecessors: Array<TaskDependencyInfo> = [],
  code = '',
  isCritical = false,
  completed = 0,
): TaskWithTagsResp {
  return {
    id,
    name,
    code,
    duration,
    predecessors,
    description: '',
    completed,
    isCritical,
    createdAt: '',
    updatedAt: '',
  }
}

function makePred(id: number, name: string, type: 'FS' | 'SS' | 'FF' = 'FS'): TaskDependencyInfo {
  return { id, code: '', name, type }
}

function buildTaskMap(tasks: TaskWithTagsResp[]): Map<number, TaskWithTagsResp> {
  return new Map(tasks.map((t) => [t.id, t]))
}

function getIds(tasks: TaskWithTagsResp[]): number[] {
  return tasks.map((t) => t.id)
}

describe('calculateStartDay', () => {
  it('returns 0 for task with no predecessors', () => {
    const task = makeTask(1, 'A', 5)
    expect(calculateStartDay(task, buildTaskMap([task]))).toBe(0)
  })

  it('returns predStart + predDuration for single predecessor', () => {
    const pred = makeTask(1, 'A', 3)
    const task = makeTask(2, 'B', 2, [makePred(1, 'A')])
    expect(calculateStartDay(task, buildTaskMap([pred, task]))).toBe(3)
  })

  it('returns max end day across multiple predecessors', () => {
    const pred1 = makeTask(1, 'A', 3)
    const pred2 = makeTask(2, 'D', 6)
    const task = makeTask(3, 'C', 1, [makePred(1, 'A'), makePred(2, 'D')])
    expect(calculateStartDay(task, buildTaskMap([pred1, pred2, task]))).toBe(6)
  })

  it('computes chained start days: A→B→C', () => {
    const a = makeTask(1, 'A', 2)
    const b = makeTask(2, 'B', 3, [makePred(1, 'A')])
    const c = makeTask(3, 'C', 1, [makePred(2, 'B')])
    const map = buildTaskMap([a, b, c])
    expect(calculateStartDay(a, map)).toBe(0)
    expect(calculateStartDay(b, map)).toBe(2)
    expect(calculateStartDay(c, map)).toBe(5)
  })
})

describe('sortTasksForGantt', () => {
  it('returns empty array for empty input', () => {
    expect(sortTasksForGantt([])).toEqual([])
  })

  it('returns single task unchanged', () => {
    const task = makeTask(1, 'A', 5)
    expect(getIds(sortTasksForGantt([task]))).toEqual([1])
  })

  it('sorts linear chain A→B→C', () => {
    const a = makeTask(1, 'A', 2)
    const b = makeTask(2, 'B', 3, [makePred(1, 'A')])
    const c = makeTask(3, 'C', 1, [makePred(2, 'B')])
    // API might return in any order; verify topological order
    expect(getIds(sortTasksForGantt([c, a, b]))).toEqual([1, 2, 3])
  })

  it('keeps independent chains each contiguous: A→B→C, D→E→F', () => {
    const a = makeTask(1, 'A', 2)
    const b = makeTask(2, 'B', 3, [makePred(1, 'A')])
    const c = makeTask(3, 'C', 1, [makePred(2, 'B')])
    const d = makeTask(4, 'D', 1)
    const e = makeTask(5, 'E', 2, [makePred(4, 'D')])
    const f = makeTask(6, 'F', 3, [makePred(5, 'E')])

    const sorted = sortTasksForGantt([f, a, e, b, d, c])
    const ids = getIds(sorted)

    // Chain 1 (ids 1,2,3) must be contiguous
    const chain1Start = ids.indexOf(1)
    expect(ids.slice(chain1Start, chain1Start + 3)).toEqual([1, 2, 3])

    // Chain 2 (ids 4,5,6) must be contiguous
    const chain2Start = ids.indexOf(4)
    expect(ids.slice(chain2Start, chain2Start + 3)).toEqual([4, 5, 6])
  })

  it('keeps branches contiguous when sharing ancestor: A→B→C, A→D→E', () => {
    const a = makeTask(1, 'A', 2)
    const b = makeTask(2, 'B', 3, [makePred(1, 'A')])
    const c = makeTask(3, 'C', 1, [makePred(2, 'B')])
    const d = makeTask(4, 'D', 1, [makePred(1, 'A')])
    const e = makeTask(5, 'E', 2, [makePred(4, 'D')])

    const sorted = sortTasksForGantt([a, b, c, d, e])
    const ids = getIds(sorted)

    // A must come first (it's the root)
    expect(ids[0]).toBe(1)

    // Branch B→C (ids 2,3) must be contiguous
    const bcStart = ids.indexOf(2)
    expect(ids.slice(bcStart, bcStart + 2)).toEqual([2, 3])

    // Branch D→E (ids 4,5) must be contiguous
    const deStart = ids.indexOf(4)
    expect(ids.slice(deStart, deStart + 2)).toEqual([4, 5])

    // Both branches must come after A
    expect(bcStart).toBeGreaterThan(0)
    expect(deStart).toBeGreaterThan(0)
  })

  it('handles diamond: A→B→D, A→C→D', () => {
    const a = makeTask(1, 'A', 2)
    const b = makeTask(2, 'B', 3, [makePred(1, 'A')])
    const c = makeTask(3, 'C', 4, [makePred(1, 'A')])
    const d = makeTask(4, 'D', 1, [makePred(2, 'B'), makePred(3, 'C')])

    const sorted = sortTasksForGantt([a, b, c, d])
    const ids = getIds(sorted)

    // A first, D last
    expect(ids[0]).toBe(1)
    expect(ids[ids.length - 1]).toBe(4)
    // B and C both appear after A and before D, each branch contiguous
    expect(ids.indexOf(2)).toBeGreaterThan(0)
    expect(ids.indexOf(3)).toBeGreaterThan(0)
  })

  it('sorts disconnected tasks with no dependencies by (startDay, id)', () => {
    const t1 = makeTask(1, 'A', 3)
    const t2 = makeTask(2, 'B', 2)
    const t3 = makeTask(3, 'C', 5)

    const sorted = sortTasksForGantt([t3, t1, t2])
    // All start at day 0, so sorted by id ascending
    expect(getIds(sorted)).toEqual([1, 2, 3])
  })

  it('maintains topological order even when input is shuffled', () => {
    const a = makeTask(1, 'A', 2)
    const b = makeTask(2, 'B', 3, [makePred(1, 'A')])
    const c = makeTask(3, 'C', 1, [makePred(2, 'B')])
    const d = makeTask(4, 'D', 1, [makePred(1, 'A')])
    const e = makeTask(5, 'E', 2, [makePred(4, 'D')])

    // Shuffle input order
    const sorted = sortTasksForGantt([e, d, c, b, a])
    const ids = getIds(sorted)

    // Every predecessor must appear before its successor
    const pos = new Map(ids.map((id, i) => [id, i]))
    for (const t of [a, b, c, d, e]) {
      for (const pred of t.predecessors ?? []) {
        expect(pos.get(pred.id)!).toBeLessThan(pos.get(t.id)!)
      }
    }
  })
})
