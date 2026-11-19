/**
 * 碳排放施工监测材料模板（xlsx）解析工具
 *
 * 模板结构（V2，三个工作表 + 选项表）：
 *   建材生产 | 建材运输 | 施工建造 | 分部工程数据
 * 前三个工作表表头一致（* 为必填列）：
 *   分部工程 | *时间 | *名称 | 规格型号 | *单位 | *数量
 * 建材运输表额外含：运输方式 | *距离（km） | *质量转换系数（导入时忽略）
 *
 * - 分部工程：用于匹配项目的施工工序
 * - 时间：Excel 日期或 YYYY-MM-DD 文本，缺省时按页面当前日期提交
 * - 名称：用于匹配资源库（项目内资源名称唯一）
 * - 阶段：由工作表名推断（建材生产/建材运输/施工建造）
 * - 旧版单表模板（建材生产 一个工作表 + 可选口径列）仍兼容
 */
import * as XLSX from 'xlsx'

export type MonitorUsageType = 'PLANNED' | 'ACTUAL'
export type MonitorStage = 'production' | 'transport' | 'construction'

export interface MonitorTemplateRow {
  /** 分部工程（匹配施工工序） */
  division: string
  /** 使用日期 YYYY-MM-DD（null = 用页面当前日期） */
  date: string | null
  /** 材料名称（匹配资源库） */
  name: string
  /** 规格型号（仅辅助展示） */
  spec: string
  /** 单位 */
  unit: string
  /** 数量 */
  quantity: number
  /** 口径（null = 用页面当前口径） */
  usageType: MonitorUsageType | null
  /** 阶段（由工作表名推断；旧版单表模板为 null） */
  stage: MonitorStage | null
}

export interface MonitorParseResult {
  rows: MonitorTemplateRow[]
  /** 行级错误（缺少名称/分部工程、数量无效等），格式：第 N 行：… */
  errors: string[]
}

/** 表头前 6 列为固定匹配依据（口径列为旧版可选第 7 列） */
const REQUIRED_HEADERS = ['分部工程', '时间', '名称', '规格型号', '单位', '数量'] as const

/** 工作表名 → 阶段 */
const SHEET_STAGE: Record<string, MonitorStage> = {
  建材生产: 'production',
  建材运输: 'transport',
  施工建造: 'construction',
  建筑建造: 'construction',
}

/** 单元格 → 去空字符串（仅处理标量；其余类型视为空） */
function norm(v: unknown): string {
  if (typeof v === 'string') return v.trim()
  if (typeof v === 'number' || typeof v === 'boolean' || typeof v === 'bigint') {
    return String(v)
  }
  return ''
}

/** 表头单元格规范化：去掉 * 必填标记与空白 */
function normalizeHeader(v: unknown): string {
  return norm(v).replace(/^\*+/, '').trim()
}

function fmtDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 时间列 → YYYY-MM-DD（支持 Date / Excel 序列号 / 文本） */
function toDateStr(v: unknown): string | null {
  if (v == null || v === '') return null
  if (v instanceof Date && !Number.isNaN(v.getTime())) return fmtDate(v)
  if (typeof v === 'number') {
    const parsed = XLSX.SSF.parse_date_code(v)
    if (parsed) return fmtDate(new Date(parsed.y, parsed.m - 1, parsed.d))
    return null
  }
  const m = norm(v).match(/(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})/)
  if (m?.[1] && m[2] && m[3]) {
    return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`
  }
  return null
}

function parseUsageType(v: unknown): MonitorUsageType | null {
  const s = norm(v)
  if (s.includes('实际')) return 'ACTUAL'
  if (s.includes('计划')) return 'PLANNED'
  return null
}

interface MonitorSheet {
  stage: MonitorStage | null
  grid: unknown[][]
}

/**
 * 读取工作簿全部工作表为二维数组（首行表头 + 数据行）。
 * 不使用 cellDates：日期列保持 Excel 序列号，由 toDateStr 经 SSF 解析，
 * 避免 SheetJS 按 UTC 构造 Date 在本地时区产生日期偏移。
 */
function readSheets(data: ArrayBuffer): MonitorSheet[] {
  const wb = XLSX.read(data, { type: 'array' })
  return wb.SheetNames.map((name) => ({
    stage: SHEET_STAGE[norm(name)] ?? null,
    grid: XLSX.utils.sheet_to_json<unknown[]>(wb.Sheets[name]!, {
      header: 1,
      defval: null,
      raw: true,
    }),
  })).filter((s) => s.grid.length > 0)
}

/** 表头是否匹配监测材料模板（* 必填标记归一化后比较） */
function headersMatch(grid: unknown[][]): boolean {
  const header = (grid[0] ?? []).map(normalizeHeader)
  return REQUIRED_HEADERS.every((h, i) => header[i] === h)
}

/** 判断上传文件是否匹配监测材料模板（任一工作表表头命中即可） */
export function isMonitorMaterialTemplate(data: ArrayBuffer): boolean {
  try {
    return readSheets(data).some((s) => headersMatch(s.grid))
  } catch {
    return false
  }
}

/** 解析监测材料模板：遍历全部匹配工作表（三阶段表各自归因），汇总为结构化行 */
export function parseMonitorMaterialTemplate(data: ArrayBuffer): MonitorParseResult {
  const rows: MonitorTemplateRow[] = []
  const errors: string[] = []

  for (const sheet of readSheets(data)) {
    if (!headersMatch(sheet.grid)) continue
    const [, ...grid] = sheet.grid

    grid.forEach((cells, idx) => {
      const line = idx + 2
      const division = norm(cells[0])
      const name = norm(cells[2])
      const qtyRaw = cells[5]

      // 整行空白跳过（模板说明行、空行）
      if (!division && !name && (qtyRaw == null || qtyRaw === '')) return

      if (!division) {
        errors.push(`第 ${line} 行：缺少分部工程`)
        return
      }
      if (!name) {
        errors.push(`第 ${line} 行：缺少材料名称`)
        return
      }
      const quantity = typeof qtyRaw === 'number' ? qtyRaw : Number(norm(qtyRaw))
      if (!Number.isFinite(quantity)) {
        errors.push(`第 ${line} 行：数量无效（${norm(qtyRaw) || '空'}）`)
        return
      }

      rows.push({
        division,
        date: toDateStr(cells[1]),
        name,
        spec: norm(cells[3]),
        unit: norm(cells[4]),
        quantity,
        usageType: parseUsageType(cells[6]),
        stage: sheet.stage,
      })
    })
  }

  return { rows, errors }
}
