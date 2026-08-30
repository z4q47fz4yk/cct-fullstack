/**
 * 数字 / 单位格式化工具
 *
 * 替代散落的 `.toFixed()` 写法，统一使用 Intl.NumberFormat('zh-CN') 加千分位。
 *
 * 精度约定（全站统一，勿在业务代码里直接 toFixed）：
 *   - 成本（元 → 万元）  ：2 位小数      → fmtWanYuan（入参为元，内部 ÷10000）
 *   - 工期（天）        ：1 位小数      → fmtDays
 *   - 碳排放 ≥ 10000kg  ：t，2 位小数  → fmtEmission
 *   - 碳排放 < 10000kg  ：kg，整数千分位 → fmtEmission
 *   - 百分比            ：1 位小数      → fmtPct
 *   - 普通整数          ：千分位        → fmtInt / fmtNumber
 */

/** 数字本地化（默认带千分位） */
export function fmtNumber(n: number, fractionDigits = 0): string {
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(n)
}

/** 整数（带千分位，无小数） */
export function fmtInt(n: number): string {
  return fmtNumber(n, 0)
}

/** 百分比（0.123 → "12.3%"） */
export function fmtPct(n: number, fractionDigits = 1): string {
  return `${fmtNumber(n * 100, fractionDigits)}%`
}

/** 碳排放：>=10000 时显示 t（2 位小数），否则 kg（整数千分位） */
export function fmtEmission(kg: number): { value: string; unit: string } {
  if (kg >= 10000) {
    return { value: fmtNumber(kg / 1000, 2), unit: 't CO₂e' }
  }
  return { value: fmtNumber(kg, 0), unit: 'kg CO₂e' }
}

/** 工期：天（保留 1 位小数，千分位） */
export function fmtDays(days: number): string {
  return `${fmtNumber(days, 1)} 天`
}

/** 货币：元 → 万元（2 位小数，不带符号，单位由父组件决定） */
export function fmtWanYuan(amount: number, fractionDigits = 2): string {
  return fmtNumber(amount / 10000, fractionDigits)
}
