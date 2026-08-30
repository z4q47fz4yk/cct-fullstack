import { describe, expect, it } from 'vite-plus/test'
import { fmtEmission, fmtWanYuan } from '@/utils/format'

describe('fmtWanYuan', () => {
  it('将元换算为万元并保留 2 位小数', () => {
    expect(fmtWanYuan(123456.78)).toBe('12.35')
  })

  it('零值显示为 0.00', () => {
    expect(fmtWanYuan(0)).toBe('0.00')
  })

  it('负值正常显示（带负号）', () => {
    expect(fmtWanYuan(-5000)).toBe('-0.50')
  })
})

describe('fmtEmission', () => {
  it('≥10000kg 转为 t 并保留 2 位小数', () => {
    expect(fmtEmission(25000)).toEqual({ value: '25.00', unit: 't CO₂e' })
  })

  it('<10000kg 保留 kg 整数千分位', () => {
    expect(fmtEmission(5000)).toEqual({ value: '5,000', unit: 'kg CO₂e' })
  })
})
