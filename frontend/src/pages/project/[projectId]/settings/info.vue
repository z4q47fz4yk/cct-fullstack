<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useQuery } from '@pinia/colada'
import { useForm, useIsFormDirty, useIsFormValid } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import * as v from 'valibot'
import { formatHttpError } from '@/utils/error'
import { useProjectApi } from '@/composables/useProjectApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { vProjectUpdate } from '@/client'
import SearchableSelect from '@/components/common/SearchableSelect.vue'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import type { Resource } from '@/types/resource'
import type { SelectOption } from '@/types/select'
import {
  FIRE_RESISTANCE_LEVEL_OPTIONS,
  FOUNDATION_LEVEL_OPTIONS,
  PILE_FOUNDATION_LEVEL_OPTIONS,
  SAFETY_LEVEL_OPTIONS,
  SEISMIC_INTENSITY_OPTIONS,
  STRUCTURE_TYPE_OPTIONS,
  WATERPROOF_LEVEL_OPTIONS,
} from '@/constants/projectSettings'
import regionData from '@/assets/china_region_data.json'

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

// 表单 schema：复用后端生成的 vProjectUpdate（约束零漂移），仅覆盖 name 为必填
const formSchema = toTypedSchema(
  v.object({
    ...vProjectUpdate.entries,
    name: v.pipe(v.string(), v.minLength(1), v.maxLength(100)),
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
  },
})
const isDirty = useIsFormDirty()
const isValid = useIsFormValid()

const [name, nameAttrs] = defineField('name')
const [description, descriptionAttrs] = defineField('description')
const [isActive, isActiveAttrs] = defineField('is_active')
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

// 把项目数据归一为表单值，同时作为「取消」恢复用的快照
function snapshotFromProject(p: NonNullable<typeof project.value>) {
  return {
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

// 结构形式数组的 computed 包装：defineField 推断为 string[] | null | undefined，
// v-model + checkbox 需要稳定的 string[]；初始值与快照已保证 []，此处归一。
const structureTypesArray = computed<string[]>({
  get: () => structureTypes.value ?? [],
  set: (next) => setFieldValue('structure_types', next),
})

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
  try {
    await updateProject({
      ...values,
      description: values.description?.trim() === '' ? null : (values.description ?? null),
      structure_types: values.structure_types?.length ? values.structure_types : null,
      address: values.address?.trim() === '' ? null : (values.address ?? null),
    })
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
  <Teleport defer to="#header-actions">
    <div
      v-if="project && !isLoadingProject && !projectError && isDirty"
      class="flex items-center gap-2"
    >
      <button
        type="button"
        class="btn btn-ghost px-4"
        aria-label="取消项目信息修改"
        :disabled="isUpdatingProject"
        @click="handleCancel"
      >
        取消
      </button>
      <button
        type="button"
        class="btn btn-primary px-5"
        aria-label="保存项目信息"
        :disabled="isUpdatingProject || !isValid || !isDirty"
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
  </Teleport>

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
      <form
        id="project-info-form"
        class="panel panel-grid grid-cols-1 xl:grid-cols-2 overflow-hidden"
        aria-label="项目信息表单"
        @submit.prevent="submit"
      >
        <!-- 基本信息 -->
        <section class="p-4 xl:row-span-2" aria-labelledby="basic-info-title">
          <h2 id="basic-info-title" class="section-title">基本信息</h2>

          <div class="space-y-4">
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
              <span v-if="errors.name" class="mt-1 text-xs text-error">{{ errors.name }}</span>
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
                rows="4"
              />
              <span v-if="errors.description" class="mt-1 text-xs text-error">
                {{ errors.description }}
              </span>
            </div>

            <div class="fieldset">
              <span class="fieldset-label">项目状态</span>
              <input
                v-model="isActive"
                v-bind="isActiveAttrs"
                :disabled="isUpdatingProject"
                class="sr-only"
                type="checkbox"
                tabindex="-1"
                aria-hidden="true"
              />
              <div
                class="flex w-full gap-1 rounded-field border border-base-content/10 bg-base-content/5 p-1 shadow-inner"
                role="group"
                aria-label="项目状态"
              >
                <button
                  type="button"
                  class="h-9 flex-1 rounded-field px-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  :class="{
                    'bg-primary/15 text-primary shadow-sm': isActive,
                    'text-fg-muted hover:bg-base-content/5 hover:text-base-content': !isActive,
                  }"
                  :disabled="isUpdatingProject"
                  :aria-pressed="isActive"
                  :aria-label="isActive ? '当前状态：进行中' : '设置项目状态为进行中'"
                  @click="isActive = true"
                >
                  进行中
                </button>
                <button
                  type="button"
                  class="h-9 flex-1 rounded-field px-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  :class="{
                    'bg-primary/15 text-primary shadow-sm': !isActive,
                    'text-fg-muted hover:bg-base-content/5 hover:text-base-content': isActive,
                  }"
                  :disabled="isUpdatingProject"
                  :aria-pressed="!isActive"
                  @click="isActive = false"
                >
                  已完成
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- 项目规模 -->
        <section class="p-4" aria-labelledby="project-scale-title">
          <h2 id="project-scale-title" class="section-title">项目规模</h2>
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
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
              <span v-if="errors.land_area" class="mt-1 text-xs text-error">
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
              <span v-if="errors.building_area" class="mt-1 text-xs text-error">
                {{ errors.building_area }}
              </span>
            </div>
          </div>
        </section>

        <!-- 临时用房 -->
        <section class="p-4" aria-labelledby="housing-title">
          <h2 id="housing-title" class="section-title">临时用房</h2>

          <div class="space-y-4">
            <div class="fieldset">
              <label class="fieldset-label" for="housing-resource">
                临时用房资源（用于碳排放与资金计算）
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
              <span v-if="errors.housing_resource_id" class="mt-1 text-xs text-error">
                {{ errors.housing_resource_id }}
              </span>
            </div>

            <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div class="fieldset">
                <label class="fieldset-label" for="housing-safety-factor">安全系数</label>
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
                <span class="mt-1 text-xs text-fg-muted">建议值不低于 1.0</span>
                <span v-if="errors.housing_safety_factor" class="mt-1 text-xs text-error">
                  {{ errors.housing_safety_factor }}
                </span>
              </div>

              <div class="fieldset">
                <label class="fieldset-label" for="persons-per-room">每间人数</label>
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
                <span class="mt-1 text-xs text-fg-muted">请输入正整数</span>
                <span v-if="errors.persons_per_room" class="mt-1 text-xs text-error">
                  {{ errors.persons_per_room }}
                </span>
              </div>
            </div>
          </div>
        </section>

        <!-- 生命周期与水电 -->
        <section class="p-4" aria-labelledby="lifecycle-title">
          <h2 id="lifecycle-title" class="section-title">生命周期与水电</h2>

          <div class="space-y-4">
            <div class="fieldset">
              <label class="fieldset-label" for="project-status">项目状态</label>
              <select
                id="project-status"
                v-model="status"
                v-bind="statusAttrs"
                :disabled="isUpdatingProject"
                class="select select-bordered w-full max-w-xs"
              >
                <option value="PLANNING">计划中</option>
                <option value="CONSTRUCTION">施工中</option>
                <option value="COMPLETED">已完成</option>
              </select>
              <span class="mt-1 text-xs text-fg-muted">
                标记为「已完成」将解锁评价阶段；与 is_active 自动同步
              </span>
            </div>

            <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div class="fieldset">
                <label class="fieldset-label" for="water-resource">水资源（水电桶）</label>
                <SearchableSelect
                  id="water-resource"
                  v-model:selected-value="waterResourceId"
                  v-model:search="utilitySearchKeyword"
                  v-bind="waterResourceIdAttrs"
                  :options="utilityResourceOptions"
                  placeholder="选择水资源"
                  :disabled="isUpdatingProject"
                />
                <span v-if="errors.water_resource_id" class="mt-1 text-xs text-error">
                  {{ errors.water_resource_id }}
                </span>
              </div>

              <div class="fieldset">
                <label class="fieldset-label" for="electricity-resource">电力资源（水电桶）</label>
                <SearchableSelect
                  id="electricity-resource"
                  v-model:selected-value="electricityResourceId"
                  v-model:search="utilitySearchKeyword"
                  v-bind="electricityResourceIdAttrs"
                  :options="utilityResourceOptions"
                  placeholder="选择电力资源"
                  :disabled="isUpdatingProject"
                />
                <span v-if="errors.electricity_resource_id" class="mt-1 text-xs text-error">
                  {{ errors.electricity_resource_id }}
                </span>
              </div>
            </div>
          </div>
        </section>

        <!-- 项目地点 -->
        <section class="p-4" aria-labelledby="location-title">
          <h2 id="location-title" class="section-title">项目地点</h2>

          <div class="space-y-4">
            <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div class="fieldset">
                <label class="fieldset-label" for="province"> 省份 </label>
                <select
                  id="province"
                  v-model="selectedProvince"
                  v-bind="provinceAttrs"
                  :disabled="isUpdatingProject"
                  class="select select-bordered w-full"
                  :class="{ 'select-error': errors.province }"
                >
                  <option :value="null">请选择省份</option>
                  <option v-for="p in provinceOptions" :key="p" :value="p">
                    {{ p }}
                  </option>
                </select>
                <span v-if="errors.province" class="mt-1 text-xs text-error">
                  {{ errors.province }}
                </span>
              </div>

              <div class="fieldset">
                <label class="fieldset-label" for="city"> 城市 </label>
                <select
                  id="city"
                  v-model="city"
                  v-bind="cityAttrs"
                  :disabled="isUpdatingProject || !selectedProvince"
                  class="select select-bordered w-full"
                  :class="{ 'select-error': errors.city }"
                >
                  <option :value="null">请选择城市</option>
                  <option v-for="c in cityOptions" :key="c" :value="c">
                    {{ c }}
                  </option>
                </select>
                <span v-if="errors.city" class="mt-1 text-xs text-error">
                  {{ errors.city }}
                </span>
              </div>
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
              <span v-if="errors.address" class="mt-1 text-xs text-error">
                {{ errors.address }}
              </span>
            </div>
          </div>
        </section>

        <!-- 建筑概况 -->
        <section class="p-4" aria-labelledby="building-overview-title">
          <h2 id="building-overview-title" class="section-title">建筑概况</h2>

          <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div class="fieldset">
              <label class="fieldset-label" for="underground-building-area"
                >地下建筑面积（m²）</label
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
              <span v-if="errors.underground_building_area" class="mt-1 text-xs text-error">
                {{ errors.underground_building_area }}
              </span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label" for="aboveground-building-area"
                >地上建筑面积（m²）</label
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
              <span v-if="errors.aboveground_building_area" class="mt-1 text-xs text-error">
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
              <span class="mt-1 text-xs text-fg-muted">地下 + 地上，自动计算</span>
            </div>
          </div>
        </section>

        <!-- 结构概况 -->
        <section class="p-4 xl:col-span-2" aria-labelledby="structure-title">
          <h2 id="structure-title" class="section-title">结构概况</h2>

          <div class="space-y-4">
            <!-- 结构形式标签 -->
            <div class="fieldset">
              <label class="fieldset-label">各楼宇结构形式</label>
              <div class="flex flex-wrap gap-2">
                <label
                  v-for="option in STRUCTURE_TYPE_OPTIONS"
                  :key="option"
                  class="flex cursor-pointer items-center gap-2 rounded-field border border-base-content/10 bg-base-content/5 px-3 py-2 transition-colors hover:bg-base-content/10"
                  :class="{
                    'border-primary/30 bg-primary/10': structureTypesArray.includes(option),
                  }"
                >
                  <input
                    type="checkbox"
                    :value="option"
                    v-model="structureTypesArray"
                    v-bind="structureTypesAttrs"
                    :disabled="isUpdatingProject"
                    class="checkbox checkbox-sm checkbox-primary"
                  />
                  <span class="text-sm">{{ option }}</span>
                </label>
              </div>
              <span v-if="errors.structure_types" class="mt-1 text-xs text-error">
                {{ errors.structure_types }}
              </span>
            </div>

            <div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
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
                <span v-if="errors.prefabrication_rate" class="mt-1 text-xs text-error">
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
                <span v-if="errors.design_service_life" class="mt-1 text-xs text-error">
                  {{ errors.design_service_life }}
                </span>
              </div>

              <div class="fieldset">
                <label class="fieldset-label" for="structural-safety-level">结构安全等级</label>
                <select
                  id="structural-safety-level"
                  v-model="structuralSafetyLevel"
                  v-bind="structuralSafetyLevelAttrs"
                  :disabled="isUpdatingProject"
                  class="select select-bordered w-full"
                  :class="{ 'select-error': errors.structural_safety_level }"
                >
                  <option :value="null">请选择</option>
                  <option v-for="opt in SAFETY_LEVEL_OPTIONS" :key="opt" :value="opt">
                    {{ opt }}
                  </option>
                </select>
                <span v-if="errors.structural_safety_level" class="mt-1 text-xs text-error">
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
                  class="select select-bordered w-full"
                  :class="{ 'select-error': errors.foundation_design_level }"
                >
                  <option :value="null">请选择</option>
                  <option v-for="opt in FOUNDATION_LEVEL_OPTIONS" :key="opt" :value="opt">
                    {{ opt }}
                  </option>
                </select>
                <span v-if="errors.foundation_design_level" class="mt-1 text-xs text-error">
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
                  class="select select-bordered w-full"
                  :class="{ 'select-error': errors.pile_foundation_design_level }"
                >
                  <option :value="null">请选择</option>
                  <option v-for="opt in PILE_FOUNDATION_LEVEL_OPTIONS" :key="opt" :value="opt">
                    {{ opt }}
                  </option>
                </select>
                <span v-if="errors.pile_foundation_design_level" class="mt-1 text-xs text-error">
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
                  class="select select-bordered w-full"
                  :class="{ 'select-error': errors.fire_resistance_level }"
                >
                  <option :value="null">请选择</option>
                  <option v-for="opt in FIRE_RESISTANCE_LEVEL_OPTIONS" :key="opt" :value="opt">
                    {{ opt }}
                  </option>
                </select>
                <span v-if="errors.fire_resistance_level" class="mt-1 text-xs text-error">
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
                  class="select select-bordered w-full"
                  :class="{ 'select-error': errors.seismic_fortification_intensity }"
                >
                  <option :value="null">请选择</option>
                  <option v-for="opt in SEISMIC_INTENSITY_OPTIONS" :key="opt" :value="opt">
                    {{ opt }}
                  </option>
                </select>
                <span v-if="errors.seismic_fortification_intensity" class="mt-1 text-xs text-error">
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
                  class="select select-bordered w-full"
                  :class="{ 'select-error': errors.underground_waterproof_level }"
                >
                  <option :value="null">请选择</option>
                  <option v-for="opt in WATERPROOF_LEVEL_OPTIONS" :key="opt" :value="opt">
                    {{ opt }}
                  </option>
                </select>
                <span v-if="errors.underground_waterproof_level" class="mt-1 text-xs text-error">
                  {{ errors.underground_waterproof_level }}
                </span>
              </div>
            </div>
          </div>
        </section>

        <!-- 工期 -->
        <section class="p-4" aria-labelledby="timeline-title">
          <h2 id="timeline-title" class="section-title">工期</h2>

          <div class="space-y-4">
            <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div class="fieldset">
                <label class="fieldset-label" for="planned-start-date">拟开工日期</label>
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
                <span v-if="errors.planned_start_date" class="mt-1 text-xs text-error">
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
                <span v-if="errors.planned_completion_date" class="mt-1 text-xs text-error">
                  {{ errors.planned_completion_date }}
                </span>
              </div>
            </div>

            <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div class="fieldset">
                <label class="fieldset-label" for="actual-start-date">实际开工日期</label>
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
                <span v-if="errors.actual_start_date" class="mt-1 text-xs text-error">
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
                <span v-if="errors.actual_completion_date" class="mt-1 text-xs text-error">
                  {{ errors.actual_completion_date }}
                </span>
              </div>
            </div>
          </div>
        </section>

        <!-- 碳排放指标 -->
        <section class="p-4" aria-labelledby="carbon-title">
          <h2 id="carbon-title" class="section-title">碳排放指标</h2>

          <div class="fieldset">
            <label class="fieldset-label" for="carbon-emission-limit">
              施工阶段总碳排放量限额（tCO₂e）
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
            <span v-if="errors.construction_carbon_emission_limit" class="mt-1 text-xs text-error">
              {{ errors.construction_carbon_emission_limit }}
            </span>
          </div>
        </section>

        <!-- 保存错误保留在表单附近，方便定位问题 -->
        <div v-if="updateError" class="alert alert-error xl:col-span-2" role="alert">
          <span class="material-symbols-outlined" aria-hidden="true">error</span>
          <span>保存失败：{{ updateErrorMessage }}</span>
        </div>
      </form>

      <p class="text-center text-xs text-fg-muted">
        最后更新：{{ formatDateTime(project.updated_at) }}
      </p>
    </div>
  </template>
</template>
