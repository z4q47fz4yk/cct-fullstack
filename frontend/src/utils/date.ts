/**
 * 本地时区日期工具
 *
 * 业务日期一律使用本地时区（YYYY-MM-DD）。
 * 勿用 `new Date().toISOString()` —— 其返回 UTC 时间，在东八区 00:00–08:00 会取到「昨天」，
 * 导致日报进度日期、实际工期等按日期计算的业务出现一天偏移。
 */
export function todayIsoLocal(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

/** N 天前的本地日期（YYYY-MM-DD），例如 daysAgoIsoLocal(2) = 前天 */
export function daysAgoIsoLocal(daysAgo: number): string {
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}
