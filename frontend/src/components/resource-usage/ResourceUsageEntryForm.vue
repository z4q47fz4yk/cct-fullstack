<script setup lang="ts">
/**
 * ResourceUsageEntryForm - 单条资源使用量录入/编辑模态框
 *
 * 支持两种模式：
 * - mode='create'：使用 vResourceUsageCreate 校验
 * - mode='update'：使用 vResourceUsageUpdate 校验
 *
 * 字段：任务（下拉）、资源分类（标签）+ 资源（下拉）、数量
 * 日期在表格顶部统一管理，不在此表单中
 */
import { computed, ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import { vResourceUsageBatchItem, vResourceUsageUpdate } from '@/client/valibot.gen'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useResourceApi } from '@/composables/useResourceApi'
import type { ResourceCategory } from '@/types/resource'
import type { ResourceUsageBatchItem, ResourceUsageUpdate, UsageType } from '@/client/types.gen'
import ResourceCategoryTabs from '@/components/resource/ResourceCategoryTabs.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { todayIsoLocal } from '@/utils/date'

const showModal = defineModel<boolean>('show', { required: true })

const { mode, initialValue, usageDate, usageType, isSubmitting, error, title, lockedTaskId } =
  defineProps<{
    mode: 'create' | 'update'
    initialValue?: ResourceUsageBatchItem | ResourceUsageUpdate | null
    /** 录入模式下的使用日期（顶部表格共享） */
    usageDate?: string
    /** 当前 batch 的用量类型（实际 / 计划） */
    usageType?: UsageType
    isSubmitting?: boolean
    error?: string
    title: string
    /** 锁定工序（如每工序内「+补充」直接补充，免选工序） */
    lockedTaskId?: number
  }>()

const emit = defineEmits<{
  submit: [data: ResourceUsageBatchItem | ResourceUsageUpdate]
  cancel: []
}>()

// 当前选中的资源分类（用于过滤资源下拉）
const activeCategory = ref<ResourceCategory>('labor')

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
const { apiResources } = useResourceApi({
  category: activeCategory,
  name: ref(''),
  page: ref(1),
  pageSize: ref(1000),
})

// 资源 Map（用于显示单位）
const resourceMap = computed(() => {
  const m = new Map<number, { name: string; unit: string; category: ResourceCategory }>()
  for (const r of apiResources.value) {
    m.set(r.id, { name: r.name, unit: r.unit, category: r.category })
  }
  return m
})

const selectedResourceUnit = computed(() => {
  if (!resourceId.value) return ''
  return resourceMap.value.get(resourceId.value)?.unit || ''
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
      const rId = v.resource_id ?? v.resourceId
      if (rId) {
        const r = resourceMap.value.get(rId)
        if (r) activeCategory.value = r.category
      }
    }
  },
  { immediate: true },
)

// 监听 modal 打开
watch(showModal, (open) => {
  if (!open) {
    resetForm()
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
  <BaseModal v-model:open="showModal" :title="title" class="max-w-lg" @close="closeModal">
    <form class="space-y-4" @submit.prevent="onSubmit">
      <!-- 任务 -->
      <fieldset class="fieldset">
        <label class="fieldset-label">工序（任务）</label>
        <select
          v-model="taskId"
          v-bind="taskIdAttrs"
          :disabled="isSubmitting || lockedTaskId !== undefined"
          class="select select-bordered w-full"
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
        <span v-if="errors.task_id" class="text-xs text-error mt-1">
          {{ errors.task_id }}
        </span>
      </fieldset>

      <!-- 资源分类标签 + 资源下拉 -->
      <fieldset class="fieldset">
        <label class="fieldset-label">资源分类</label>
        <ResourceCategoryTabs
          :selected-category="activeCategory"
          :disabled="isSubmitting"
          @update:selected-category="(v) => v != null && (activeCategory = v)"
        />
      </fieldset>
      <fieldset class="fieldset">
        <label class="fieldset-label">资源</label>
        <select
          v-model="resourceId"
          v-bind="resourceIdAttrs"
          :disabled="isSubmitting"
          class="select select-bordered w-full"
          :class="{ 'select-error': errors.resource_id }"
        >
          <option :value="0" disabled>请选择资源</option>
          <option v-for="r in apiResources" :key="r.id" :value="r.id">
            {{ r.name }} ({{ r.unit }})
          </option>
        </select>
        <span v-if="errors.resource_id" class="text-xs text-error mt-1">
          {{ errors.resource_id }}
        </span>
      </fieldset>

      <!-- 数量 -->
      <fieldset class="fieldset">
        <label class="fieldset-label">
          {{ usageType === 'PLANNED' ? '计划使用量' : '实际使用量' }}
        </label>
        <label class="input w-full">
          <input
            v-model.number="quantity"
            v-bind="quantityAttrs"
            :disabled="isSubmitting"
            class="w-full"
            :class="{ 'input-error': errors.quantity }"
            min="0.01"
            step="0.01"
            type="number"
            placeholder="0.00"
          />
          <span class="text-sm text-fg-muted">{{ selectedResourceUnit }}</span>
        </label>
        <span v-if="errors.quantity" class="text-xs text-error mt-1">
          {{ errors.quantity }}
        </span>
      </fieldset>

      <!-- 错误提示 -->
      <div v-if="error" class="alert alert-error alert-sm">
        <span class="material-symbols-outlined icon-sm">error</span>
        <span class="text-sm">{{ error }}</span>
      </div>

      <!-- 操作按钮 -->
      <div class="modal-action">
        <button type="button" class="btn btn-ghost" :disabled="isSubmitting" @click="closeModal">
          取消
        </button>
        <button type="submit" class="btn btn-primary" :disabled="isSubmitting || !meta.valid">
          <span v-if="isSubmitting" class="loading loading-spinner loading-xs"></span>
          <span>保存</span>
        </button>
      </div>
    </form>
  </BaseModal>
</template>
