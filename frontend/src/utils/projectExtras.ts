/**
 * 项目前端扩展字段（本地存储）
 *
 * 设计稿要求但后端暂未提供接口的字段（碳排放分项指标 / 成本指标 / 建筑类型 / 项目图片），
 * 按项目维度存入 localStorage，与 HTML 原型的本地存储方式一致。
 * 后端接入后应迁移为项目字段 + 上传接口，本地存储不能替代服务端持久化。
 */

export interface ProjectExtras {
  building_type: string | null
  carbon_emission_limit_production: number | null
  carbon_emission_limit_transport: number | null
  carbon_emission_limit_construction: number | null
  total_cost_limit: number | null
  image_data: string | null
}

export const PROJECT_EXTRAS_DEFAULT: ProjectExtras = {
  building_type: null,
  carbon_emission_limit_production: null,
  carbon_emission_limit_transport: null,
  carbon_emission_limit_construction: null,
  total_cost_limit: null,
  image_data: null,
}

const storageKey = (projectId: number | string) => `cct-project-extras-${projectId}`

export function loadProjectExtras(projectId: number | string | null | undefined): ProjectExtras {
  if (projectId === null || projectId === undefined) return { ...PROJECT_EXTRAS_DEFAULT }
  try {
    const raw = localStorage.getItem(storageKey(projectId))
    if (!raw) return { ...PROJECT_EXTRAS_DEFAULT }
    const parsed = JSON.parse(raw) as Partial<ProjectExtras>
    return { ...PROJECT_EXTRAS_DEFAULT, ...parsed }
  } catch {
    return { ...PROJECT_EXTRAS_DEFAULT }
  }
}

export function saveProjectExtras(
  projectId: number | string,
  extras: Partial<ProjectExtras>,
): void {
  try {
    const merged = { ...loadProjectExtras(projectId), ...extras }
    localStorage.setItem(storageKey(projectId), JSON.stringify(merged))
  } catch {
    // 存储满 / 隐私模式等场景静默失败，不阻断表单提交
  }
}
