<script setup lang="ts">
/**
 * ResourceUsageEntryForm - 单条资源使用量录入/编辑模态框（设计稿 modal-entry-row）
 *
 * 字段与顺序对齐设计稿：使用日期 / 工序 / 资源名称 / 用量 / 单位 /
 * 单价（元）/ 成本（元）/ 碳排放因子 / 碳排放量(tCO₂)。
 * 单位、单价、因子随资源自动带出；成本 = 用量 × 单价、
 * 碳排放量 = 用量 × 因子 / 1000 自动计算（只读灰底，设计稿同款）。
 *
 * 提交数据仍只含 task_id / resource_id / quantity（后端契约），
 * 日期沿用顶部表格的统一使用日期。
 */
import { computed, ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import { useQuery } from '@pinia/colada'
import { vResourceUsageBatchItem, vResourceUsageUpdate } from '@/client/valibot.gen'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import type { ResourceUsageBatchItem, ResourceUsageUpdate, UsageType } from '@/client/types.gen'
import BaseModal from '@/components/ui/BaseModal.vue'
import { todayIsoLocal } from '@/utils/date'
import { fmtNumber } from '@/utils/format'
import {
  usageStageOf,
  USAGE_STAGE_LABEL,
  USAGE_STAGE_FILTER_OPTIONS,
  type UsageStage,
} from '@/utils/usageStage'

const showModal = defineModel<boolean>('show', { required: true })

const { mode, initialValue, usageDate, usageType, isSubmitting, error, title, lockedTaskId } =
  defineProps<{
    mode: 'create' | 'update'
    initialValue?: ResourceUsageBatchItem | ResourceUsageUpdate | null
    /** 录入模式下的使用日期（顶部表格共享，设计稿同字段只读展示） */
    usageDate?: string
    /** 当前 batch 的用量类型（实际 / 计划） */
    usageType?: UsageType
    isSubmitting?: boolean
    error?: string
    title: string
    /** 锁定工序（免选工序） */
    lockedTaskId?: number
  }>()

const emit = defineEmits<{
  submit: [data: ResourceUsageBatchItem | ResourceUsageUpdate]
  cancel: []
}>()

// 根据模式选择 schema
const validationSchema = computed(() =>
  mode === 'create' ? vResourceUsageBatchItem : vResourceUsageUpdate,
)

const { handleSubmit, errors, setValues, meta, resetForm, defineField } = useForm({
  validationSchema: toTypedSchema(validationSchema.value),
  initialValues: {
    task_id: 0,
    resource_id: 0,
    quantity: 0,
    usage_date: todayIsoLocal(),
  },
})

const [taskId, taskIdAttrs] = defineField('task_id')
const [resourceId, resourceIdAttrs] = defineField('resource_id')
const [quantity, quantityAttrs] = defineField('quantity')

// 数据源
const { tasks } = useScheduleApi()
const { currentProjectId } = useProjectContext()
const { state: resourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: FETCH_ALL_PAGE_SIZE },
  }),
)
const apiResources = computed(() => resourcesState.value?.data?.items ?? [])

// ─── 阶段选项：过滤资源下拉（与列表「阶段」列同口径） ──────────
const stage = ref<UsageStage | 'all'>('all')

const filteredResources = computed(() =>
  stage.value === 'all'
    ? apiResources.value
    : apiResources.value.filter((r) => usageStageOf(r.name, r.category) === stage.value),
)

// 切换阶段后，已选资源若不在该阶段则清空重选
watch(stage, () => {
  const rid = Number(resourceId.value)
  if (rid && !filteredResources.value.some((r) => r.id === rid)) {
    setValues({ resource_id: 0 })
  }
})

// 资源 Map（单位 / 单价 / 碳排放因子随资源自动带出）
const resourceMap = computed(() => {
  const m = new Map<number, { name: string; unit: string; unitPrice: number; carbonFactor: number }>()
  for (const r of apiResources.value) {
    m.set(r.id, { name: r.name, unit: r.unit, unitPrice: r.unitPrice, carbonFactor: r.carbonFactor })
  }
  return m
})

const selectedResource = computed(() =>
  resourceId.value ? resourceMap.value.get(Number(resourceId.value)) : undefined,
)

/** 自动计算：成本（元）= 用量 × 单价 */
const computedCost = computed(() => {
  const res = selectedResource.value
  const qty = Number(quantity.value) || 0
  if (!res || qty <= 0) return ''
  return fmtNumber(qty * res.unitPrice, 2)
})

/** 自动计算：碳排放量（tCO₂）= 用量 × 因子 / 1000 */
const computedEmission = computed(() => {
  const res = selectedResource.value
  const qty = Number(quantity.value) || 0
  if (!res || qty <= 0) return ''
  return fmtNumber((qty * res.carbonFactor) / 1000, 2)
})

// 同步 initialValue 变化到表单
watch(
  [() => lockedTaskId, () => initialValue],
  ([locked, val]) => {
    const lockedId = locked ?? null
    if (lockedId !== null) {
      setValues({ task_id: lockedId })
    }
    if (val) {
      const v = val as ResourceUsageBatchItem & ResourceUsageUpdate
      setValues({
        task_id: lockedId ?? v.task_id ?? v.taskId ?? 0,
        resource_id: v.resource_id ?? v.resourceId ?? 0,
        quantity: v.quantity ?? 0,
      })
    }
  },
  { immediate: true },
)

// 监听 modal 打开
watch(showModal, (open) => {
  if (!open) {
    resetForm()
    stage.value = 'all'
  }
})

const onSubmit = handleSubmit(() => {
  if (mode === 'create') {
    const data: ResourceUsageBatchItem = {
      task_id: lockedTaskId ?? (Number(taskId.value) || 0),
      resource_id: Number(resourceId.value) || 0,
      usage_date: usageDate || todayIsoLocal(),
      quantity: Number(quantity.value) || 0,
    }
    emit('submit', data)
  } else {
    const data: ResourceUsageUpdate = {
      taskId: Number(taskId.value) || undefined,
      resourceId: Number(resourceId.value) || undefined,
      quantity: Number(quantity.value) || undefined,
    }
    emit('submit', data)
  }
})

function closeModal() {
  showModal.value = false
  emit('cancel')
}
</script>

<template>
  <BaseModal v-model:open="showModal" :title="title" @close="closeModal">
    <form class="form-grid" @submit.prevent="onSubmit">
      <!-- 使用日期（设计稿字段，随顶部表格统一日期，只读） -->
      <fieldset class="fieldset">
        <label class="fieldset-label">
          使用日期 <span class="text-error" aria-hidden="true">*</span>
        </label>
        <input class="input w-full" type="date" :value="usageDate || todayIsoLocal()" disabled />
      </fieldset>

      <!-- 工序 -->
      <fieldset class="fieldset">
        <label class="fieldset-label">工序</label>
        <select
          v-model="taskId"
          v-bind="taskIdAttrs"
          :disabled="isSubmitting || lockedTaskId !== undefined"
          class="select w-full"
          :class="{ 'select-error': errors.task_id }"
        >
          <option v-if="lockedTaskId !== undefined" :value="lockedTaskId" selected>
            {{ tasks.find((t) => t.id === lockedTaskId)?.code }}
            {{ tasks.find((t) => t.id === lockedTaskId)?.name ?? `工序 #${lockedTaskId}` }}
          </option>
          <option :value="0" disabled>请选择工序</option>
          <option v-for="t in tasks" :key="t.id" :value="t.id">
            {{ t.code ? `${t.code} - ${t.name}` : t.name }}
          </option>
        </select>
        <span v-if="errors.task_id" class="text-xs text-error">{{ errors.task_id }}</span>
      </fieldset>

      <!-- 阶段（过滤资源范围，与列表「阶段」列同口径） -->
      <fieldset class="fieldset">
        <label class="fieldset-label">阶段</label>
        <select v-model="stage" class="select w-full" :disabled="isSubmitting">
          <option v-for="o in USAGE_STAGE_FILTER_OPTIONS" :key="o.value" :value="o.value">
            {{ o.label }}
          </option>
        </select>
      </fieldset>

      <!-- 资源名称（按所选阶段过滤） -->
      <fieldset class="fieldset">
        <label class="fieldset-label">资源名称</label>
        <select
          v-model="resourceId"
          v-bind="resourceIdAttrs"
          :disabled="isSubmitting"
          class="select w-full"
          :class="{ 'select-error': errors.resource_id }"
        >
          <option :value="0" disabled>请选择资源</option>
          <option v-for="r in filteredResources" :key="r.id" :value="r.id">
            {{ r.name }}
          </option>
        </select>
        <span v-if="errors.resource_id" class="text-xs text-error">{{ errors.resource_id }}</span>
      </fieldset>

      <!-- 用量 -->
      <fieldset class="fieldset">
        <label class="fieldset-label">
          用量 <span class="text-error" aria-hidden="true">*</span>
        </label>
        <label class="input w-full" :class="{ 'input-error': errors.quantity }">
          <input
            v-model.number="quantity"
            v-bind="quantityAttrs"
            :disabled="isSubmitting"
            class="w-full bg-transparent outline-none"
            min="0.01"
            step="0.01"
            type="number"
            placeholder="请输入用量"
          />
          <span class="text-sm text-fg-muted">{{ selectedResource?.unit || '' }}</span>
        </label>
        <span v-if="errors.quantity" class="text-xs text-error">{{ errors.quantity }}</span>
      </fieldset>

      <!-- 单位（自动带出，只读） -->
      <fieldset class="fieldset">
        <label class="fieldset-label">单位</label>
        <input class="input w-full" :value="selectedResource?.unit || ''" disabled />
      </fieldset>

      <!-- 单价（元）（自动带出，只读） -->
      <fieldset class="fieldset">
        <label class="fieldset-label">单价（元）</label>
        <input
          class="input w-full"
          :value="selectedResource ? fmtNumber(selectedResource.unitPrice, 2) : ''"
          disabled
        />
      </fieldset>

      <!-- 成本（元）（自动计算，只读） -->
      <fieldset class="fieldset">
        <label class="fieldset-label">成本（元）</label>
        <input class="input w-full" :value="computedCost" placeholder="用量 × 单价，自动计算" disabled />
      </fieldset>

      <!-- 碳排放因子（自动带出，只读） -->
      <fieldset class="fieldset">
        <label class="fieldset-label">碳排放因子</label>
        <input
          class="input w-full"
          :value="selectedResource ? selectedResource.carbonFactor.toFixed(4) : ''"
          disabled
        />
      </fieldset>

      <!-- 碳排放量(tCO₂)（自动计算，只读） -->
      <fieldset class="fieldset">
        <label class="fieldset-label">碳排放量(tCO₂)</label>
        <input class="input w-full" :value="computedEmission" placeholder="自动计算" disabled />
      </fieldset>

      <!-- 错误提示 -->
      <div v-if="error" class="alert alert-error alert-sm full">
        <span class="material-symbols-outlined icon-sm">error</span>
        <span class="text-sm">{{ error }}</span>
      </div>

      <!-- 操作按钮 -->
      <div class="modal-action full">
        <button type="button" class="btn btn-outline" :disabled="isSubmitting" @click="closeModal">
          取消
        </button>
        <button type="submit" class="btn btn-primary" :disabled="isSubmitting || !meta.valid">
          <span v-if="isSubmitting" class="loading loading-spinner loading-xs"></span>
          <span>确定</span>
        </button>
      </div>
    </form>
  </BaseModal>
</template>

<style scoped>
/* 设计稿 form-grid：两列等宽；full = 整行（错误提示/按钮区） */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px 16px;
}
.form-grid .full {
  grid-column: 1 / -1;
}
</style>
