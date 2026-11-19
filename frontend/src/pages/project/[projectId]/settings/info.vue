<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useQuery } from '@pinia/colada'
import { useForm, useIsFormDirty } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import * as v from 'valibot'
import { formatHttpError } from '@/utils/error'
import { useProjectApi } from '@/composables/useProjectApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { vProjectUpdate } from '@/client'
import PageHead from '@/components/common/PageHead.vue'
import SearchableSelect from '@/components/common/SearchableSelect.vue'
import SegmentControl from '@/components/common/SegmentControl.vue'
import ResourcesView from './resources.vue'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import type { Resource } from '@/types/resource'
import type { SelectOption } from '@/types/select'
import {
  BUILDING_TYPE_OPTIONS,
  FIRE_RESISTANCE_LEVEL_OPTIONS,
  FOUNDATION_LEVEL_OPTIONS,
  PILE_FOUNDATION_LEVEL_OPTIONS,
  SAFETY_LEVEL_OPTIONS,
  SEISMIC_INTENSITY_OPTIONS,
  STRUCTURE_TYPE_OPTIONS,
  WATERPROOF_LEVEL_OPTIONS,
} from '@/constants/projectSettings'
import regionData from '@/assets/china_region_data.json'
import { loadProjectExtras, saveProjectExtras } from '@/utils/projectExtras'

definePage({
  meta: {
    title: '项目信息',
    icon: 'info',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 2,
  },
})

const {
  project,
  isLoadingProject,
  projectError,
  refreshProject,
  updateProject,
  isUpdatingProject,
  updateError,
} = useProjectApi()
const { currentProjectId } = useProjectContext()
const { notifyError, notifySuccess } = useToast()

// 临时用房可选资源（项目范围内全部资源，按关键字服务端过滤）
const searchKeyword = ref('')

const { state: housingResState } = useQuery(() => ({
  ...listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: {
      name: searchKeyword.value || undefined,
      per_page: FETCH_ALL_PAGE_SIZE,
      category: 'material',
    },
  }),
  enabled: currentProjectId.value !== null,
}))

const housingResources = computed(() => housingResState.value?.data?.items ?? [])

const housingResourceOptions = computed<SelectOption<Resource, number | null>[]>(() =>
  housingResources.value.map((r) => ({
    raw: r,
    value: r.id,
    label: r.name,
    description: `${r.category} · ${r.unit}`,
  })),
)

// 水电资源（项目范围内全部资源，按关键字服务端过滤）
const utilitySearchKeyword = ref('')
const { state: utilityResState } = useQuery(() => ({
  ...listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: {
      name: utilitySearchKeyword.value || undefined,
      per_page: FETCH_ALL_PAGE_SIZE,
    },
  }),
  enabled: currentProjectId.value !== null,
}))
const utilityResources = computed(() => utilityResState.value?.data?.items ?? [])
const utilityResourceOptions = computed<SelectOption<Resource, number | null>[]>(() =>
  utilityResources.value.map((r) => ({
    raw: r,
    value: r.id,
    label: r.name,
    description: `${r.category} · ${r.unit}`,
  })),
)

// 省市数据
const regionMap = regionData as Record<string, string[]>
const provinceOptions = Object.keys(regionMap)
const selectedProvince = ref<string | null>(null)
const cityOptions = computed(() => {
  if (!selectedProvince.value) return []
  return regionMap[selectedProvince.value] ?? []
})

// 必填校验辅助：类型保持 nullish（与现有 null 值管线兼容），但 null/undefined 不通过。
// 星号与这里的规则一一对应（验收：正式表单能阻止无效提交）。
const isPresent = <T>(val: T | null | undefined): val is T => val !== null && val !== undefined
const REQUIRED_MSG = '此项为必填'

const formSchema = toTypedSchema(
  v.object({
    ...vProjectUpdate.entries,
    name: v.pipe(v.string(), v.minLength(1), v.maxLength(100)),
    // 地下/地上建筑面积：非负数字，必填（无地下建筑时允许 0）
    underground_building_area: v.pipe(
      v.nullish(v.pipe(v.number(), v.minValue(0))),
      v.check(isPresent, REQUIRED_MSG),
    ),
    aboveground_building_area: v.pipe(
      v.nullish(v.pipe(v.number(), v.minValue(0))),
      v.check(isPresent, REQUIRED_MSG),
    ),
    // 建设地点：省份 + 城市必选
    province: v.pipe(
      v.nullish(v.pipe(v.string(), v.minLength(1))),
      v.check(isPresent, REQUIRED_MSG),
    ),
    city: v.pipe(
      v.nullish(v.pipe(v.string(), v.minLength(1))),
      v.check(isPresent, REQUIRED_MSG),
    ),
    // 拟开工 / 实际开工日期必填
    planned_start_date: v.pipe(
      v.nullish(v.pipe(v.string(), v.isoDate())),
      v.check(isPresent, REQUIRED_MSG),
    ),
    actual_start_date: v.pipe(
      v.nullish(v.pipe(v.string(), v.isoDate())),
      v.check(isPresent, REQUIRED_MSG),
    ),
    // 临时用房资源必选
    housing_resource_id: v.pipe(
      v.nullish(v.pipe(v.number(), v.integer())),
      v.check(isPresent, REQUIRED_MSG),
    ),
    // 安全系数（业务下限 1.0）与每间人数（正整数）
    housing_safety_factor: v.pipe(
      v.nullish(v.pipe(v.number(), v.minValue(1))),
      v.check(isPresent, REQUIRED_MSG),
    ),
    persons_per_room: v.pipe(
      v.nullish(v.pipe(v.number(), v.integer(), v.minValue(1))),
      v.check(isPresent, REQUIRED_MSG),
    ),
    // 施工阶段碳排放总量指标：非负数字，必填
    construction_carbon_emission_limit: v.pipe(
      v.nullish(v.pipe(v.number(), v.minValue(0))),
      v.check(isPresent, REQUIRED_MSG),
    ),
    // 施工阶段总成本指标（万元）：非负数字，必填
    total_cost_limit: v.pipe(
      v.nullish(v.pipe(v.number(), v.minValue(0))),
      v.check(isPresent, REQUIRED_MSG),
    ),
    // 项目图片：必须存在有效图片（已有图片即满足）
    image_data: v.pipe(v.nullish(v.string()), v.check(isPresent, REQUIRED_MSG)),
    // ── 前端扩展字段（本地存储，后端暂无接口；字段名与后续后端契约保持一致） ──
    building_type: v.nullish(v.pipe(v.string(), v.maxLength(20))),
    carbon_emission_limit_production: v.nullish(v.pipe(v.number(), v.minValue(0))),
    carbon_emission_limit_transport: v.nullish(v.pipe(v.number(), v.minValue(0))),
    carbon_emission_limit_construction: v.nullish(v.pipe(v.number(), v.minValue(0))),
  }),
)

const { handleSubmit, errors, defineField, resetForm, setFieldValue } = useForm({
  validationSchema: formSchema,
  initialValues: {
    name: '',
    description: '',
    is_active: true,
    status: 'CONSTRUCTION',
    land_area: null,
    building_area: null,
    housing_resource_id: null,
    water_resource_id: null,
    electricity_resource_id: null,
    housing_safety_factor: 1.2,
    persons_per_room: 4,
    province: null,
    city: null,
    address: null,
    latitude: null,
    longitude: null,
    underground_building_area: null,
    aboveground_building_area: null,
    structure_types: [],
    prefabrication_rate: 30,
    design_service_life: 50,
    structural_safety_level: '二级',
    foundation_design_level: '乙级',
    pile_foundation_design_level: null,
    fire_resistance_level: '二级',
    seismic_fortification_intensity: '7度',
    underground_waterproof_level: '一级',
    planned_start_date: null,
    planned_completion_date: null,
    actual_start_date: null,
    actual_completion_date: null,
    construction_carbon_emission_limit: null,
    building_type: null,
    carbon_emission_limit_production: null,
    carbon_emission_limit_transport: null,
    carbon_emission_limit_construction: null,
    total_cost_limit: null,
    image_data: null,
  },
})
const isDirty = useIsFormDirty()

const [name, nameAttrs] = defineField('name')
const [description, descriptionAttrs] = defineField('description')
const [status, statusAttrs] = defineField('status')
const [landArea, landAreaAttrs] = defineField('land_area')
const [buildingArea, buildingAreaAttrs] = defineField('building_area')
const [housingResourceId, housingResourceIdAttrs] = defineField('housing_resource_id')
const [waterResourceId, waterResourceIdAttrs] = defineField('water_resource_id')
const [electricityResourceId, electricityResourceIdAttrs] = defineField('electricity_resource_id')
// NOT NULL 字段：schema 为 optional（省略=不修改），但表单内空输入以 null 标记，
// 使 vee-validate 校验拦截（无效的类型），避免"清空却静默不改"的歧义
const [housingSafetyFactor, housingSafetyFactorAttrs] = defineField<
  'housing_safety_factor',
  number | null
>('housing_safety_factor')
const [personsPerRoom, personsPerRoomAttrs] = defineField<'persons_per_room', number | null>(
  'persons_per_room',
)
const [province, provinceAttrs] = defineField('province')
const [city, cityAttrs] = defineField('city')
const [address, addressAttrs] = defineField('address')
const [latitude, latitudeAttrs] = defineField('latitude')
const [longitude, longitudeAttrs] = defineField('longitude')
const [undergroundBuildingArea, undergroundBuildingAreaAttrs] = defineField(
  'underground_building_area',
)
const [abovegroundBuildingArea, abovegroundBuildingAreaAttrs] = defineField(
  'aboveground_building_area',
)
const [structureTypes, structureTypesAttrs] = defineField('structure_types')
const [prefabricationRate, prefabricationRateAttrs] = defineField('prefabrication_rate')
const [designServiceLife, designServiceLifeAttrs] = defineField('design_service_life')
const [structuralSafetyLevel, structuralSafetyLevelAttrs] = defineField('structural_safety_level')
const [foundationDesignLevel, foundationDesignLevelAttrs] = defineField('foundation_design_level')
const [pileFoundationDesignLevel, pileFoundationDesignLevelAttrs] = defineField(
  'pile_foundation_design_level',
)
const [fireResistanceLevel, fireResistanceLevelAttrs] = defineField('fire_resistance_level')
const [seismicFortificationIntensity, seismicFortificationIntensityAttrs] = defineField(
  'seismic_fortification_intensity',
)
const [undergroundWaterproofLevel, undergroundWaterproofLevelAttrs] = defineField(
  'underground_waterproof_level',
)
const [plannedStartDate, plannedStartDateAttrs] = defineField('planned_start_date')
const [plannedCompletionDate, plannedCompletionDateAttrs] = defineField('planned_completion_date')
const [actualStartDate, actualStartDateAttrs] = defineField('actual_start_date')
const [actualCompletionDate, actualCompletionDateAttrs] = defineField('actual_completion_date')
const [constructionCarbonEmissionLimit, constructionCarbonEmissionLimitAttrs] = defineField(
  'construction_carbon_emission_limit',
)
const [buildingType, buildingTypeAttrs] = defineField('building_type')
const [carbonLimitProduction, carbonLimitProductionAttrs] = defineField(
  'carbon_emission_limit_production',
)
const [carbonLimitTransport, carbonLimitTransportAttrs] = defineField(
  'carbon_emission_limit_transport',
)
const [carbonLimitConstruction, carbonLimitConstructionAttrs] = defineField(
  'carbon_emission_limit_construction',
)
const [totalCostLimit, totalCostLimitAttrs] = defineField('total_cost_limit')
const [imageData] = defineField('image_data')

// 把项目数据归一为表单值（后端字段 + 前端扩展字段合并），同时作为「取消」恢复用的快照
function snapshotFromProject(p: NonNullable<typeof project.value>) {
  return {
    ...loadProjectExtras(p.id),
    name: p.name,
    description: p.description ?? '',
    is_active: p.is_active,
    status: p.status ?? 'CONSTRUCTION',
    land_area: p.land_area,
    building_area: p.building_area,
    housing_resource_id: p.housing_resource_id,
    water_resource_id: p.water_resource_id,
    electricity_resource_id: p.electricity_resource_id,
    housing_safety_factor: p.housing_safety_factor ?? 1.2,
    persons_per_room: p.persons_per_room ?? 4,
    province: p.province ?? null,
    city: p.city ?? null,
    address: p.address ?? null,
    latitude: p.latitude ?? null,
    longitude: p.longitude ?? null,
    underground_building_area: p.underground_building_area,
    aboveground_building_area: p.aboveground_building_area,
    structure_types: p.structure_types ?? [],
    prefabrication_rate: p.prefabrication_rate ?? 30,
    design_service_life: p.design_service_life ?? 50,
    structural_safety_level: p.structural_safety_level ?? '二级',
    foundation_design_level: p.foundation_design_level ?? '乙级',
    pile_foundation_design_level: p.pile_foundation_design_level ?? null,
    fire_resistance_level: p.fire_resistance_level ?? '二级',
    seismic_fortification_intensity: p.seismic_fortification_intensity ?? '7度',
    underground_waterproof_level: p.underground_waterproof_level ?? '一级',
    planned_start_date: p.planned_start_date ?? null,
    planned_completion_date: p.planned_completion_date ?? null,
    actual_start_date: p.actual_start_date ?? null,
    actual_completion_date: p.actual_completion_date ?? null,
    construction_carbon_emission_limit: p.construction_carbon_emission_limit,
  }
}

const formSnapshot = ref<ReturnType<typeof snapshotFromProject> | null>(null)

watch(
  project,
  (p) => {
    if (!p) return
    const snap = snapshotFromProject(p)
    formSnapshot.value = snap
    resetForm({ values: snap })
    // 同步省市选择状态
    selectedProvince.value = snap.province
  },
  { immediate: true },
)

// 省份变化时同步表单并按需清空城市（oldProvince 用于识别用户主动切换）
watch(selectedProvince, (newProvince, oldProvince) => {
  setFieldValue('province', newProvince)
  if (oldProvince !== null && oldProvince !== newProvince) {
    setFieldValue('city', null)
  }
})

// 项目总建筑面积（地下 + 地上，自动汇总）
const totalBuildingArea = computed(() => {
  const u = undergroundBuildingArea.value ?? 0
  const a = abovegroundBuildingArea.value ?? 0
  return u + a
})

// 结构形式（设计稿为单选下拉）：界面单选 ↔ 接口数组契约（选中项存为单元素数组，
// 未选择存 []；提交时统一归一为 null）。原数组中若有多项，未修改时原样保留。
const structureTypeSingle = computed<string>({
  get: () => structureTypes.value?.[0] ?? '',
  set: (v) => setFieldValue('structure_types', v ? [v] : []),
})

// ─── 项目图片（设计稿：预览 + 选择/更换，≤3MB JPG/PNG/WebP） ──────
const imagePreview = computed(() => imageData.value ?? '')
const imageStatus = ref('')
const imageFileInput = ref<HTMLInputElement | null>(null)

function openImagePicker() {
  imageFileInput.value?.click()
}

/** 独立保存项目图片：立即写入本地存储并同步碳排数据看板 */
function saveProjectImage() {
  if (!imageData.value) {
    imageStatus.value = '请先选择图片。'
    return
  }
  if (currentProjectId.value === null) return
  saveProjectExtras(currentProjectId.value, { image_data: imageData.value })
  imageStatus.value = '项目图片已保存，数据看板已同步。'
  notifySuccess({ title: '项目图片已保存' })
}

function handleImageFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  imageStatus.value = ''
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 3 * 1024 * 1024) {
    imageStatus.value = '请选择不超过 3 MB 的 JPG、PNG 或 WebP 图片。'
    input.value = ''
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = typeof reader.result === 'string' ? reader.result : ''
    if (!dataUrl) {
      imageStatus.value = '文件读取失败，请重试。'
      return
    }
    setFieldValue('image_data', dataUrl)
    imageStatus.value = '图片已更新，保存后生效。'
  }
  reader.onerror = () => {
    imageStatus.value = '文件读取失败，请重试。'
  }
  reader.readAsDataURL(file)
  input.value = ''
}

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', { hour12: false })
}

// 可空数字输入：空字符串归一为 null（HTML number input 没有原生的 null 表达）
function parseNullableNumber(raw: string): number | null {
  const trimmed = raw.trim()
  if (trimmed === '') return null
  const n = Number(trimmed)
  return Number.isNaN(n) ? null : n
}

const submit = handleSubmit(async (values) => {
  // 悬浮按钮保持可点击：请求进行中重复点击直接忽略（不通过禁用表达）
  if (isUpdatingProject.value) return
  try {
    // 后端字段：显式列出（契约字段，随 generate-api 更新）
    await updateProject({
      name: values.name,
      is_active: values.is_active,
      status: values.status,
      description: values.description?.trim() === '' ? null : (values.description ?? null),
      land_area: values.land_area,
      building_area: values.building_area,
      province: values.province,
      city: values.city,
      address: values.address?.trim() === '' ? null : (values.address ?? null),
      latitude: values.latitude,
      longitude: values.longitude,
      underground_building_area: values.underground_building_area,
      aboveground_building_area: values.aboveground_building_area,
      structure_types: values.structure_types?.length ? values.structure_types : null,
      prefabrication_rate: values.prefabrication_rate,
      design_service_life: values.design_service_life,
      structural_safety_level: values.structural_safety_level,
      foundation_design_level: values.foundation_design_level,
      pile_foundation_design_level: values.pile_foundation_design_level,
      fire_resistance_level: values.fire_resistance_level,
      seismic_fortification_intensity: values.seismic_fortification_intensity,
      underground_waterproof_level: values.underground_waterproof_level,
      planned_start_date: values.planned_start_date,
      planned_completion_date: values.planned_completion_date,
      actual_start_date: values.actual_start_date,
      actual_completion_date: values.actual_completion_date,
      construction_carbon_emission_limit: values.construction_carbon_emission_limit,
      housing_resource_id: values.housing_resource_id,
      water_resource_id: values.water_resource_id,
      electricity_resource_id: values.electricity_resource_id,
      // 必填字段已通过校验（非空），此处归一为后端非空契约
      housing_safety_factor: values.housing_safety_factor ?? 1.2,
      persons_per_room: values.persons_per_room ?? 4,
    })
    // 前端扩展字段（后端暂无接口）：按项目维度存本地存储
    if (currentProjectId.value !== null) {
      saveProjectExtras(currentProjectId.value, {
        building_type: values.building_type,
        carbon_emission_limit_production: values.carbon_emission_limit_production,
        carbon_emission_limit_transport: values.carbon_emission_limit_transport,
        carbon_emission_limit_construction: values.carbon_emission_limit_construction,
        total_cost_limit: values.total_cost_limit,
        image_data: values.image_data,
      })
    }
    notifySuccess({ title: '项目信息已保存' })
  } catch (error) {
    const description = formatHttpError(error, '请稍后重试')
    notifyError({ title: '保存失败', description })
    console.error('Failed to update project information:', error)
  }
})

function handleCancel() {
  if (formSnapshot.value) {
    resetForm({ values: formSnapshot.value })
    selectedProvince.value = formSnapshot.value.province
  }
}

// ─── 页内 Tab：项目概况 / 基础数据（设计稿 view-info） ──────────
const activeTab = ref<'overview' | 'basedata'>('overview')

// 解析后端校验错误为可读字符串
const updateErrorMessage = computed(() =>
  updateError.value ? formatHttpError(updateError.value, '请稍后重试') : '',
)

// ─── 路由离开守卫：拦截未保存的修改 ────────────────────────────
const { confirmWarn } = useConfirm()
onBeforeRouteLeave(async () => {
  if (!isDirty.value) return true
  const r = await confirmWarn('您有未保存的修改，确定要离开吗？离开后修改将丢失。', '未保存的修改')
  return r.confirmed
})
</script>

<template>
  <!-- 加载骨架 -->
  <div v-if="isLoadingProject" class="flex justify-center py-8">
    <div role="status" aria-label="正在加载项目信息">
      <span class="loading loading-spinner loading-lg text-primary" />
    </div>
  </div>

  <!-- 错误 -->
  <div v-else-if="projectError" class="panel border border-error/20" role="alert">
    <div class="flex flex-col items-center justify-center gap-3 py-8 text-center">
      <span class="material-symbols-outlined icon-2xl text-error" aria-hidden="true">error</span>
      <div>
        <h2 class="font-semibold text-base-content">加载项目信息失败</h2>
        <p class="mt-1 text-sm text-fg-muted">请检查网络连接后重试</p>
      </div>
      <button class="btn btn-primary btn-sm" type="button" @click="refreshProject()">重试</button>
    </div>
  </div>

  <template v-else-if="project">
    <div class="space-y-4">
      <!-- 页头（设计稿 view-info page-head：常驻 取消 / 保存 toolbar） -->
      <PageHead title="项目信息" subtitle="项目基本参数与建设概况">
        <!-- 悬浮操作条：固定在视口右上角（顶栏下方），不随页面滚动；
             按钮不禁用（校验失败时 vee-validate 会阻止提交并标出错误项） -->
        <div class="actions-float">
          <button
            type="button"
            class="btn btn-ghost px-4"
            aria-label="取消项目信息修改"
            @click="handleCancel"
          >
            取消
          </button>
          <button
            type="button"
            class="btn btn-primary px-5"
            aria-label="保存项目信息"
            @click="submit"
          >
            <span
              v-if="isUpdatingProject"
              class="loading loading-spinner loading-xs"
              aria-hidden="true"
            />
            <span>{{ isUpdatingProject ? '保存中' : '保存' }}</span>
          </button>
        </div>
      </PageHead>

      <!-- 页内 Tab（设计稿：项目概况 / 基础数据） -->
      <SegmentControl
        v-model="activeTab"
        :options="[
          { value: 'overview', label: '项目概况', icon: 'info' },
          { value: 'basedata', label: '基础数据', icon: 'database' },
        ]"
        aria-label="项目信息页签"
      />

      <!-- 项目概况：纵向堆叠分组卡片（设计稿 view-info，每组 4 列表单网格） -->
      <form
        v-show="activeTab === 'overview'"
        id="project-info-form"
        class="flex flex-col gap-4"
        aria-label="项目信息表单"
        @submit.prevent="submit"
      >
        <!-- 基本信息 -->
        <section class="panel p-0" aria-labelledby="basic-info-title">
          <div class="card-head">
            <h2 id="basic-info-title" class="section-title m-0">基本信息</h2>
          </div>
          <div class="card-body grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div class="fieldset">
              <label class="fieldset-label" for="project-name">
                项目名称 <span class="text-error" aria-hidden="true">*</span>
              </label>
              <input
                id="project-name"
                v-model="name"
                v-bind="nameAttrs"
                :disabled="isUpdatingProject"
                class="input w-full"
                :class="{ 'input-error': errors.name }"
                placeholder="例如：某某高速公路项目"
                type="text"
                aria-required="true"
              />
              <span v-if="errors.name" class="text-xs text-error">{{ errors.name }}</span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="project-status">
                项目状态 <span class="text-error" aria-hidden="true">*</span>
              </label>
              <select
                id="project-status"
                v-model="status"
                v-bind="statusAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.status }"
              >
                <option value="PLANNING">计划中</option>
                <option value="CONSTRUCTION">施工中</option>
                <option value="COMPLETED">已完成</option>
              </select>
              <span v-if="errors.status" class="text-xs text-error">{{ errors.status }}</span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="project-description">项目描述</label>
              <textarea
                id="project-description"
                v-model="description"
                v-bind="descriptionAttrs"
                :disabled="isUpdatingProject"
                class="textarea w-full"
                :class="{ 'textarea-error': errors.description }"
                placeholder="可选，简要描述项目内容"
                rows="3"
              />
              <span v-if="errors.description" class="text-xs text-error">
                {{ errors.description }}
              </span>
            </div>
          </div>
        </section>

        <!-- 建筑概况 -->
        <section class="panel p-0" aria-labelledby="building-overview-title">
          <div class="card-head">
            <h2 id="building-overview-title" class="section-title m-0">建筑概况</h2>
          </div>
          <div class="card-body grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div class="fieldset">
              <label class="fieldset-label" for="underground-building-area"
                >地下建筑面积（m²）<span class="text-error" aria-hidden="true">*</span></label
              >
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.underground_building_area }"
              >
                <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
                  foundation
                </span>
                <input
                  id="underground-building-area"
                  :value="undergroundBuildingArea ?? ''"
                  v-bind="undergroundBuildingAreaAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  @input="
                    (e) =>
                      (undergroundBuildingArea = parseNullableNumber(
                        (e.target as HTMLInputElement).value,
                      ))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">m²</span>
              </label>
              <span v-if="errors.underground_building_area" class="text-xs text-error">
                {{ errors.underground_building_area }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="aboveground-building-area"
                >地上建筑面积（m²）<span class="text-error" aria-hidden="true">*</span></label
              >
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.aboveground_building_area }"
              >
                <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
                  apartment
                </span>
                <input
                  id="aboveground-building-area"
                  :value="abovegroundBuildingArea ?? ''"
                  v-bind="abovegroundBuildingAreaAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  @input="
                    (e) =>
                      (abovegroundBuildingArea = parseNullableNumber(
                        (e.target as HTMLInputElement).value,
                      ))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">m²</span>
              </label>
              <span v-if="errors.aboveground_building_area" class="text-xs text-error">
                {{ errors.aboveground_building_area }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="building-area-summary">项目总建筑面积（m²）</label>
              <div
                id="building-area-summary"
                class="input flex w-full items-center gap-2 bg-base-content/5"
                aria-live="polite"
              >
                <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
                  domain
                </span>
                <span class="flex-1 text-base-content">
                  {{ totalBuildingArea > 0 ? totalBuildingArea : '—' }}
                </span>
                <span class="shrink-0 text-sm text-fg-muted">m²</span>
              </div>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="land-area">占地面积（m²）</label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.land_area }"
              >
                <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
                  grid_view
                </span>
                <input
                  id="land-area"
                  :value="landArea ?? ''"
                  v-bind="landAreaAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  @input="
                    (e) => (landArea = parseNullableNumber((e.target as HTMLInputElement).value))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">m²</span>
              </label>
              <span v-if="errors.land_area" class="text-xs text-error">
                {{ errors.land_area }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="building-area">建筑面积（m²）</label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.building_area }"
              >
                <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
                  apartment
                </span>
                <input
                  id="building-area"
                  :value="buildingArea ?? ''"
                  v-bind="buildingAreaAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  @input="
                    (e) =>
                      (buildingArea = parseNullableNumber((e.target as HTMLInputElement).value))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">m²</span>
              </label>
              <span v-if="errors.building_area" class="text-xs text-error">
                {{ errors.building_area }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="province">
                省份 <span class="text-error" aria-hidden="true">*</span>
              </label>
              <select
                id="province"
                v-model="selectedProvince"
                v-bind="provinceAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.province }"
              >
                <option :value="null">请选择省份</option>
                <option v-for="p in provinceOptions" :key="p" :value="p">
                  {{ p }}
                </option>
              </select>
              <span v-if="errors.province" class="text-xs text-error">
                {{ errors.province }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="city">
                城市 <span class="text-error" aria-hidden="true">*</span>
              </label>
              <select
                id="city"
                v-model="city"
                v-bind="cityAttrs"
                :disabled="isUpdatingProject || !selectedProvince"
                class="select w-full"
                :class="{ 'select-error': errors.city }"
              >
                <option :value="null">请选择城市</option>
                <option v-for="c in cityOptions" :key="c" :value="c">
                  {{ c }}
                </option>
              </select>
              <span v-if="errors.city" class="text-xs text-error">
                {{ errors.city }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="address">详细地址</label>
              <input
                id="address"
                v-model="address"
                v-bind="addressAttrs"
                :disabled="isUpdatingProject"
                class="input w-full"
                :class="{ 'input-error': errors.address }"
                placeholder="请输入具体地址"
                type="text"
              />
              <span v-if="errors.address" class="text-xs text-error">
                {{ errors.address }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="building-type">建筑类型</label>
              <select
                id="building-type"
                v-model="buildingType"
                v-bind="buildingTypeAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.building_type }"
              >
                <option :value="null">请选择</option>
                <option v-for="opt in BUILDING_TYPE_OPTIONS" :key="opt" :value="opt">
                  {{ opt }}
                </option>
              </select>
              <span v-if="errors.building_type" class="text-xs text-error">
                {{ errors.building_type }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="latitude">纬度（WGS84）</label>
              <input
                id="latitude"
                :value="latitude ?? ''"
                v-bind="latitudeAttrs"
                :disabled="isUpdatingProject"
                class="input w-full"
                :class="{ 'input-error': errors.latitude }"
                placeholder="如 39.9075"
                type="number"
                step="any"
                min="-90"
                max="90"
                @input="
                  (e) => (latitude = parseNullableNumber((e.target as HTMLInputElement).value))
                "
              />
              <span v-if="errors.latitude" class="text-xs text-error">
                {{ errors.latitude }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="longitude">经度（WGS84）</label>
              <input
                id="longitude"
                :value="longitude ?? ''"
                v-bind="longitudeAttrs"
                :disabled="isUpdatingProject"
                class="input w-full"
                :class="{ 'input-error': errors.longitude }"
                placeholder="如 116.39723"
                type="number"
                step="any"
                min="-180"
                max="180"
                @input="
                  (e) => (longitude = parseNullableNumber((e.target as HTMLInputElement).value))
                "
              />
              <span v-if="errors.longitude" class="text-xs text-error">
                {{ errors.longitude }}
              </span>
            </div>
          </div>
        </section>

        <!-- 工期 -->
        <section class="panel p-0" aria-labelledby="timeline-title">
          <div class="card-head">
            <h2 id="timeline-title" class="section-title m-0">工期</h2>
          </div>
          <div class="card-body grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div class="fieldset">
              <label class="fieldset-label" for="planned-start-date">
                拟开工日期 <span class="text-error" aria-hidden="true">*</span>
              </label>
              <input
                id="planned-start-date"
                :value="plannedStartDate ?? ''"
                v-bind="plannedStartDateAttrs"
                :disabled="isUpdatingProject"
                class="input w-full"
                :class="{ 'input-error': errors.planned_start_date }"
                type="date"
                @input="
                  (e) =>
                    setFieldValue(
                      'planned_start_date',
                      (e.target as HTMLInputElement).value || null,
                    )
                "
              />
              <span v-if="errors.planned_start_date" class="text-xs text-error">
                {{ errors.planned_start_date }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="planned-completion-date">拟竣工日期</label>
              <input
                id="planned-completion-date"
                :value="plannedCompletionDate ?? ''"
                v-bind="plannedCompletionDateAttrs"
                :disabled="isUpdatingProject"
                class="input w-full"
                :class="{ 'input-error': errors.planned_completion_date }"
                type="date"
                @input="
                  (e) =>
                    setFieldValue(
                      'planned_completion_date',
                      (e.target as HTMLInputElement).value || null,
                    )
                "
              />
              <span v-if="errors.planned_completion_date" class="text-xs text-error">
                {{ errors.planned_completion_date }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="actual-start-date">
                实际开工日期 <span class="text-error" aria-hidden="true">*</span>
              </label>
              <input
                id="actual-start-date"
                :value="actualStartDate ?? ''"
                v-bind="actualStartDateAttrs"
                :disabled="isUpdatingProject"
                class="input w-full"
                :class="{ 'input-error': errors.actual_start_date }"
                type="date"
                @input="
                  (e) =>
                    setFieldValue(
                      'actual_start_date',
                      (e.target as HTMLInputElement).value || null,
                    )
                "
              />
              <span v-if="errors.actual_start_date" class="text-xs text-error">
                {{ errors.actual_start_date }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="actual-completion-date">实际竣工日期</label>
              <input
                id="actual-completion-date"
                :value="actualCompletionDate ?? ''"
                v-bind="actualCompletionDateAttrs"
                :disabled="isUpdatingProject"
                class="input w-full"
                :class="{ 'input-error': errors.actual_completion_date }"
                type="date"
                @input="
                  (e) =>
                    setFieldValue(
                      'actual_completion_date',
                      (e.target as HTMLInputElement).value || null,
                    )
                "
              />
              <span v-if="errors.actual_completion_date" class="text-xs text-error">
                {{ errors.actual_completion_date }}
              </span>
            </div>
          </div>
        </section>

        <!-- 结构概况 -->
        <section class="panel p-0" aria-labelledby="structure-title">
          <div class="card-head">
            <h2 id="structure-title" class="section-title m-0">结构概况</h2>
          </div>
          <div class="card-body grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <!-- 结构形式（设计稿：下拉选，与所有字段等宽） -->
            <div class="fieldset">
              <label class="fieldset-label" for="structure-type">各楼宇结构形式</label>
              <select
                id="structure-type"
                v-model="structureTypeSingle"
                v-bind="structureTypesAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.structure_types }"
              >
                <option value="">请选择</option>
                <option v-for="option in STRUCTURE_TYPE_OPTIONS" :key="option" :value="option">
                  {{ option }}
                </option>
              </select>
              <span v-if="errors.structure_types" class="text-xs text-error">
                {{ errors.structure_types }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="structural-safety-level">结构安全等级</label>
              <select
                id="structural-safety-level"
                v-model="structuralSafetyLevel"
                v-bind="structuralSafetyLevelAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.structural_safety_level }"
              >
                <option :value="null">请选择</option>
                <option v-for="opt in SAFETY_LEVEL_OPTIONS" :key="opt" :value="opt">
                  {{ opt }}
                </option>
              </select>
              <span v-if="errors.structural_safety_level" class="text-xs text-error">
                {{ errors.structural_safety_level }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="foundation-design-level">基础设计等级</label>
              <select
                id="foundation-design-level"
                v-model="foundationDesignLevel"
                v-bind="foundationDesignLevelAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.foundation_design_level }"
              >
                <option :value="null">请选择</option>
                <option v-for="opt in FOUNDATION_LEVEL_OPTIONS" :key="opt" :value="opt">
                  {{ opt }}
                </option>
              </select>
              <span v-if="errors.foundation_design_level" class="text-xs text-error">
                {{ errors.foundation_design_level }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="pile-foundation-design-level">
                桩基设计等级（选填）
              </label>
              <select
                id="pile-foundation-design-level"
                v-model="pileFoundationDesignLevel"
                v-bind="pileFoundationDesignLevelAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.pile_foundation_design_level }"
              >
                <option :value="null">请选择</option>
                <option v-for="opt in PILE_FOUNDATION_LEVEL_OPTIONS" :key="opt" :value="opt">
                  {{ opt }}
                </option>
              </select>
              <span v-if="errors.pile_foundation_design_level" class="text-xs text-error">
                {{ errors.pile_foundation_design_level }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="fire-resistance-level">建筑耐火等级</label>
              <select
                id="fire-resistance-level"
                v-model="fireResistanceLevel"
                v-bind="fireResistanceLevelAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.fire_resistance_level }"
              >
                <option :value="null">请选择</option>
                <option v-for="opt in FIRE_RESISTANCE_LEVEL_OPTIONS" :key="opt" :value="opt">
                  {{ opt }}
                </option>
              </select>
              <span v-if="errors.fire_resistance_level" class="text-xs text-error">
                {{ errors.fire_resistance_level }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="seismic-fortification-intensity">
                抗震设防烈度
              </label>
              <select
                id="seismic-fortification-intensity"
                v-model="seismicFortificationIntensity"
                v-bind="seismicFortificationIntensityAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.seismic_fortification_intensity }"
              >
                <option :value="null">请选择</option>
                <option v-for="opt in SEISMIC_INTENSITY_OPTIONS" :key="opt" :value="opt">
                  {{ opt }}
                </option>
              </select>
              <span v-if="errors.seismic_fortification_intensity" class="text-xs text-error">
                {{ errors.seismic_fortification_intensity }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="underground-waterproof-level">
                地下工程防水等级
              </label>
              <select
                id="underground-waterproof-level"
                v-model="undergroundWaterproofLevel"
                v-bind="undergroundWaterproofLevelAttrs"
                :disabled="isUpdatingProject"
                class="select w-full"
                :class="{ 'select-error': errors.underground_waterproof_level }"
              >
                <option :value="null">请选择</option>
                <option v-for="opt in WATERPROOF_LEVEL_OPTIONS" :key="opt" :value="opt">
                  {{ opt }}
                </option>
              </select>
              <span v-if="errors.underground_waterproof_level" class="text-xs text-error">
                {{ errors.underground_waterproof_level }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="prefabrication-rate">装配率（%）</label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.prefabrication_rate }"
              >
                <input
                  id="prefabrication-rate"
                  :value="prefabricationRate ?? ''"
                  v-bind="prefabricationRateAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  placeholder="30"
                  @input="
                    (e) =>
                      (prefabricationRate = parseNullableNumber(
                        (e.target as HTMLInputElement).value,
                      ))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">%</span>
              </label>
              <span v-if="errors.prefabrication_rate" class="text-xs text-error">
                {{ errors.prefabrication_rate }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="design-service-life">设计使用年限（年）</label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.design_service_life }"
              >
                <input
                  id="design-service-life"
                  :value="designServiceLife ?? ''"
                  v-bind="designServiceLifeAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="1"
                  placeholder="50"
                  @input="
                    (e) =>
                      (designServiceLife = parseNullableNumber(
                        (e.target as HTMLInputElement).value,
                      ))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">年</span>
              </label>
              <span v-if="errors.design_service_life" class="text-xs text-error">
                {{ errors.design_service_life }}
              </span>
            </div>
          </div>
        </section>

        <!-- 临时用房 -->
        <section class="panel p-0" aria-labelledby="housing-title">
          <div class="card-head">
            <h2 id="housing-title" class="section-title m-0">临时用房</h2>
          </div>
          <div class="card-body grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div class="fieldset">
              <label class="fieldset-label" for="housing-resource">
                临时用房资源 <span class="text-error" aria-hidden="true">*</span>
              </label>
              <SearchableSelect
                id="housing-resource"
                v-model:selected-value="housingResourceId"
                v-model:search="searchKeyword"
                v-bind="housingResourceIdAttrs"
                :options="housingResourceOptions"
                placeholder="选择临时用房资源"
                :disabled="isUpdatingProject"
              />
              <span v-if="errors.housing_resource_id" class="text-xs text-error">
                {{ errors.housing_resource_id }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="housing-safety-factor">
                安全系数 <span class="text-error" aria-hidden="true">*</span>
              </label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.housing_safety_factor }"
              >
                <input
                  id="housing-safety-factor"
                  :value="housingSafetyFactor ?? ''"
                  v-bind="housingSafetyFactorAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="1"
                  step="0.05"
                  placeholder="1.2"
                  @input="
                    (e) =>
                      (housingSafetyFactor = parseNullableNumber(
                        (e.target as HTMLInputElement).value,
                      ))
                  "
                />
              </label>
              <span v-if="errors.housing_safety_factor" class="text-xs text-error">
                {{ errors.housing_safety_factor }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="persons-per-room">
                每间人数 <span class="text-error" aria-hidden="true">*</span>
              </label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.persons_per_room }"
              >
                <input
                  id="persons-per-room"
                  :value="personsPerRoom ?? ''"
                  v-bind="personsPerRoomAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="1"
                  step="1"
                  placeholder="4"
                  @input="
                    (e) =>
                      (personsPerRoom = parseNullableNumber((e.target as HTMLInputElement).value))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">人</span>
              </label>
              <span v-if="errors.persons_per_room" class="text-xs text-error">
                {{ errors.persons_per_room }}
              </span>
            </div>
          </div>
        </section>

        <!-- 水电资源 -->
        <section class="panel p-0" aria-labelledby="utility-title">
          <div class="card-head">
            <h2 id="utility-title" class="section-title m-0">水电资源</h2>
          </div>
          <div class="card-body grid grid-cols-1 gap-4 md:grid-cols-2">
            <div class="fieldset">
              <label class="fieldset-label" for="water-resource">水资源</label>
              <SearchableSelect
                id="water-resource"
                v-model:selected-value="waterResourceId"
                v-model:search="utilitySearchKeyword"
                v-bind="waterResourceIdAttrs"
                :options="utilityResourceOptions"
                placeholder="选择水资源"
                :disabled="isUpdatingProject"
              />
              <span v-if="errors.water_resource_id" class="text-xs text-error">
                {{ errors.water_resource_id }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="electricity-resource">电力资源</label>
              <SearchableSelect
                id="electricity-resource"
                v-model:selected-value="electricityResourceId"
                v-model:search="utilitySearchKeyword"
                v-bind="electricityResourceIdAttrs"
                :options="utilityResourceOptions"
                placeholder="选择电力资源"
                :disabled="isUpdatingProject"
              />
              <span v-if="errors.electricity_resource_id" class="text-xs text-error">
                {{ errors.electricity_resource_id }}
              </span>
            </div>
          </div>
        </section>


        <!-- 碳排放指标 -->
        <section class="panel p-0" aria-labelledby="carbon-title">
          <div class="card-head">
            <h2 id="carbon-title" class="section-title m-0">碳排放指标</h2>
          </div>
          <div class="card-body grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div class="fieldset">
              <label class="fieldset-label" for="carbon-emission-limit">
                施工阶段碳排放总量指标（tCO₂e）
                <span class="text-error" aria-hidden="true">*</span>
              </label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.construction_carbon_emission_limit }"
              >
                <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
                  co2
                </span>
                <input
                  id="carbon-emission-limit"
                  :value="constructionCarbonEmissionLimit ?? ''"
                  v-bind="constructionCarbonEmissionLimitAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  @input="
                    (e) =>
                      (constructionCarbonEmissionLimit = parseNullableNumber(
                        (e.target as HTMLInputElement).value,
                      ))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">tCO₂e</span>
              </label>
              <span v-if="errors.construction_carbon_emission_limit" class="text-xs text-error">
                {{ errors.construction_carbon_emission_limit }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="carbon-limit-production">
                建材生产阶段碳排放量指标（tCO₂e）
              </label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.carbon_emission_limit_production }"
              >
                <input
                  id="carbon-limit-production"
                  :value="carbonLimitProduction ?? ''"
                  v-bind="carbonLimitProductionAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  @input="
                    (e) =>
                      (carbonLimitProduction = parseNullableNumber(
                        (e.target as HTMLInputElement).value,
                      ))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">tCO₂e</span>
              </label>
              <span v-if="errors.carbon_emission_limit_production" class="text-xs text-error">
                {{ errors.carbon_emission_limit_production }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="carbon-limit-transport">
                建材运输阶段碳排放量指标（tCO₂e）
              </label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.carbon_emission_limit_transport }"
              >
                <input
                  id="carbon-limit-transport"
                  :value="carbonLimitTransport ?? ''"
                  v-bind="carbonLimitTransportAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  @input="
                    (e) =>
                      (carbonLimitTransport = parseNullableNumber(
                        (e.target as HTMLInputElement).value,
                      ))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">tCO₂e</span>
              </label>
              <span v-if="errors.carbon_emission_limit_transport" class="text-xs text-error">
                {{ errors.carbon_emission_limit_transport }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="carbon-limit-construction">
                建筑建造阶段碳排放量指标（tCO₂e）
              </label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.carbon_emission_limit_construction }"
              >
                <input
                  id="carbon-limit-construction"
                  :value="carbonLimitConstruction ?? ''"
                  v-bind="carbonLimitConstructionAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  @input="
                    (e) =>
                      (carbonLimitConstruction = parseNullableNumber(
                        (e.target as HTMLInputElement).value,
                      ))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">tCO₂e</span>
              </label>
              <span v-if="errors.carbon_emission_limit_construction" class="text-xs text-error">
                {{ errors.carbon_emission_limit_construction }}
              </span>
            </div>
          </div>
        </section>

        <!-- 成本指标 -->
        <section class="panel p-0" aria-labelledby="cost-title">
          <div class="card-head">
            <h2 id="cost-title" class="section-title m-0">成本指标</h2>
          </div>
          <div class="card-body grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div class="fieldset">
              <label class="fieldset-label" for="total-cost-limit">
                施工阶段总成本指标（万元）
                <span class="text-error" aria-hidden="true">*</span>
              </label>
              <label
                class="input flex w-full items-center gap-2"
                :class="{ 'input-error': errors.total_cost_limit }"
              >
                <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
                  payments
                </span>
                <input
                  id="total-cost-limit"
                  :value="totalCostLimit ?? ''"
                  v-bind="totalCostLimitAttrs"
                  :disabled="isUpdatingProject"
                  class="w-full bg-transparent outline-none"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  @input="
                    (e) =>
                      (totalCostLimit = parseNullableNumber((e.target as HTMLInputElement).value))
                  "
                />
                <span class="shrink-0 text-sm text-fg-muted">万元</span>
              </label>
              <span v-if="errors.total_cost_limit" class="text-xs text-error">
                {{ errors.total_cost_limit }}
              </span>
            </div>
          </div>
        </section>

        <!-- 项目图片（设计稿：位于项目概况最下方） -->
        <section class="panel p-0" aria-labelledby="project-image-title">
          <div class="card-head">
            <h2 id="project-image-title" class="section-title m-0">
              项目图片 <span class="text-error" aria-hidden="true">*</span>
            </h2>
            <div class="toolbar">
              <button
                type="button"
                class="btn btn-outline gap-1"
                :disabled="isUpdatingProject"
                @click="openImagePicker"
              >
                <span class="material-symbols-outlined icon-sm">image</span>
                选择 / 更换图片
              </button>
              <button
                type="button"
                class="btn btn-primary gap-1"
                :disabled="isUpdatingProject || !imagePreview"
                @click="saveProjectImage"
              >
                <span class="material-symbols-outlined icon-sm">save</span>
                保存图片
              </button>
            </div>
            <input
              ref="imageFileInput"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              class="hidden"
              aria-label="选择或更换项目图片"
              @change="handleImageFileChange"
            />
          </div>
          <div class="card-body">
            <img
              v-if="imagePreview"
              :src="imagePreview"
              alt="项目图片"
              class="block w-full max-w-2xl h-60 object-contain bg-base-200 rounded-field"
            />
            <div
              v-else
              class="w-full max-w-2xl h-60 flex items-center justify-center bg-base-200 rounded-field text-fg-subtle"
            >
              <div class="text-center">
                <span class="material-symbols-outlined icon-2xl" aria-hidden="true">image</span>
                <p class="text-sm mt-1">尚未上传项目图片</p>
              </div>
            </div>
            <p v-if="imageStatus" class="text-xs text-fg-muted mt-2" role="status">{{ imageStatus }}</p>
            <span v-if="errors.image_data" class="text-xs text-error block mt-2">
              {{ errors.image_data }}
            </span>
          </div>
        </section>

        <!-- 保存错误保留在表单附近，方便定位问题 -->
        <div v-if="updateError" class="alert alert-error" role="alert">
          <span class="material-symbols-outlined" aria-hidden="true">error</span>
          <span>保存失败：{{ updateErrorMessage }}</span>
        </div>
      </form>

      <p v-show="activeTab === 'overview'" class="text-center text-xs text-fg-muted">
        最后更新：{{ formatDateTime(project.updated_at) }}
      </p>

      <!-- 基础数据：资源列表（复用资源管理页，逻辑零改动） -->
      <ResourcesView v-if="activeTab === 'basedata'" />
    </div>
  </template>
</template>

<style scoped>
/* 取消/保存悬浮操作条：固定在视口右上角（顶栏 58px 之下，与主内容右边距 22px 对齐），
   不随主内容滚动，带面板底色与阴影保证可读性 */
.actions-float {
  position: fixed;
  top: 58px;
  right: 22px;
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.5rem 0.75rem;
  background: var(--color-panel);
  border: 1px solid var(--color-panel-border);
  border-radius: 0.75rem;
  box-shadow: 0 4px 12px rgb(16 24 40 / 0.1);
}
</style>
