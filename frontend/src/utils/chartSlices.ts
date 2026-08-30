import type { PieSlice } from '@/client/types.gen'
import { fmtNumber, fmtPct } from '@/utils/format'

/**
 * 按后端返回的切片顺序（PieSlice.sortOrder 升序，0 起）排序。
 * 后端已按 sortOrder 升序返回，这里做防御性显式排序。
 */
export function orderSlicesByChart(slices: PieSlice[]): PieSlice[] {
  return [...slices].sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0))
}

/** 按名称取切片值（kgCO₂e），未命中返回 0 */
export function sliceValueByName(slices: PieSlice[], name: string): number {
  return slices.find((s) => s.name === name)?.value ?? 0
}

/** kgCO₂e → tCO₂e 展示文本（2 位小数） */
export function formatTons(kg: number): string {
  return fmtNumber(kg / 1000, 2)
}

/** 占比文本（如 "52.0%"） */
export function formatPct(kg: number, total: number): string {
  if (total <= 0) return '0.0%'
  return fmtPct(kg / total, 1)
}
