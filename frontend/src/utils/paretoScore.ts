/**
 * 帕累托解加权评分
 *
 * 公式：M_i = α·T_i/ΣT + β·C_i/ΣC + γ·E_i/ΣE
 *   - α, β, γ = 用户权重（0~100）
 *   - T_i, C_i, E_i = 第 i 个解的工期(天)/成本(万元)/碳排放(kg)
 *   - ΣT, ΣC, ΣE = 全部解的总和
 *
 * 排序语义：M_i 越小越好（数值越低，方案越优）
 *   - 当权重为 0 时，该指标不参与评分
 *   - 相同 score 的解共享 rank（按原顺序 tie-break）
 *
 * 边界：
 *   - 空数组 → 返回 []
 *   - ΣT=ΣC=ΣE=0 → 所有解 score=0、rank=1
 *   - 权重全 0 → 所有解 score=0（仍按原顺序 rank=1）
 */
import type { OptimizeSolution } from '@/client/types.gen'
import type { ParetoWeights } from '@/types/paretoWeights'

export interface ScoredSolution {
  /** 原始解 */
  solution: OptimizeSolution
  /** 综合得分（越小越优） */
  score: number
  /** 排名（1-based，相同 score 同 rank） */
  rank: number
  /** 三项指标分别的贡献值（便于调试/可视化） */
  parts: {
    duration: number
    cost: number
    emission: number
  }
}

/**
 * 对 Pareto 解集按权重评分并排序
 *
 * @param solutions 全部解（顺序无关；内部按 score 重排）
 * @param weights 权重对象
 * @returns 带 score/rank 的解数组（已排序，rank=1 是最优）
 */
export function scoreSolutions(
  solutions: OptimizeSolution[],
  weights: ParetoWeights,
): ScoredSolution[] {
  if (solutions.length === 0) return []

  // 计算归一化分母（总和）
  let sumT = 0
  let sumC = 0
  let sumE = 0
  for (const s of solutions) {
    sumT += s.duration
    sumC += s.cost
    sumE += s.emission
  }

  // 计算每个解的 score 和 parts
  const scored: ScoredSolution[] = solutions.map((solution) => {
    const normT = sumT === 0 ? 0 : solution.duration / sumT
    const normC = sumC === 0 ? 0 : solution.cost / sumC
    const normE = sumE === 0 ? 0 : solution.emission / sumE

    const parts = {
      duration: weights.duration * normT,
      cost: weights.cost * normC,
      emission: weights.emission * normE,
    }
    const score = parts.duration + parts.cost + parts.emission

    return { solution, score, rank: 0, parts }
  })

  // 按 score 升序排序（相同 score 保持原顺序）
  scored.sort((a, b) => a.score - b.score)

  // 分配 rank（相同 score 同 rank）
  let currentRank = 1
  for (let i = 0; i < scored.length; i++) {
    if (i > 0 && scored[i]!.score > scored[i - 1]!.score) {
      currentRank = i + 1
    }
    scored[i]!.rank = currentRank
  }

  return scored
}
