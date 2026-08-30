<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useForm, useIsFormDirty, useIsFormValid } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import * as v from 'valibot'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useConstraintApi } from '@/composables/useConstraintApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useToast } from '@/composables/useToast'
import { formatHttpError } from '@/utils/error'
import SearchableSelect from '@/components/common/SearchableSelect.vue'
import type { ResourceConstraintResp } from '@/types/constraint'
import type { Resource } from '@/types/resource'
import type { SelectOption } from '@/types/select'

const { mode = 'create', initialValues = null } = defineProps<{
  mode?: 'create' | 'edit'
  initialValues?: ResourceConstraintResp | null
}>()

const emit = defineEmits<{
  (e: 'saved'): void
  (e: 'cancel'): void
}>()

const { createConstraint, updateConstraint } = useConstraintApi()
const { currentProjectId } = useProjectContext()
const { notifyError, notifySuccess } = useToast()

// ─── Schema ──────────────────────────────────────────────────────────
// create: resourceId 允许 null（SearchableSelect 未选时为 null，isValid 自然为 false）
const createSchema = toTypedSchema(
  v.object({
    resourceId: v.nullish(v.pipe(v.number(), v.integer(), v.minValue(0))),
    maxUsage: v.optional(v.pipe(v.number(), v.minValue(0)), 100),
    description: v.optional(v.pipe(v.string(), v.maxLength(500)), ''),
  }),
)

// edit: resourceId 用 v.optional（pre-filled，不校验）；maxUsage 必填
const editSchema = toTypedSchema(
  v.object({
    resourceId: v.optional(v.pipe(v.number(), v.integer())),
    maxUsage: v.pipe(v.number(), v.minValue(0)),
    description: v.optional(v.pipe(v.string(), v.maxLength(500)), ''),
  }),
)

const formSchema = computed(() => (mode === 'create' ? createSchema : editSchema))

// ─── Form ────────────────────────────────────────────────────────────
function computeDefaults() {
  if (mode === 'edit' && initialValues) {
    return {
      resourceId: initialValues.resourceId,
      maxUsage: initialValues.maxUsage,
      description: initialValues.description ?? '',
    }
  }
  return {
    resourceId: null,
    maxUsage: 100,
    description: '',
  }
}

const { handleSubmit, errors, defineField, resetForm, isSubmitting } = useForm({
  validationSchema: formSchema.value,
  initialValues: computeDefaults(),
})

const isDirty = useIsFormDirty()
const isValid = useIsFormValid()

const [resourceId, resourceIdAttrs] = defineField('resourceId')
const [maxUsage, maxUsageAttrs] = defineField('maxUsage')
const [description, descriptionAttrs] = defineField('description')

// props 变化时重新同步表单（用户编辑不同行时）
watch(
  () => [mode, initialValues?.id] as const,
  () => resetForm({ values: computeDefaults() }),
)

// ─── SearchableSelect ───────────────────────────────────────────────
const searchKeyword = ref('')

const { state: resourcesState, asyncStatus: resourcesStatus } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { name: searchKeyword.value || undefined },
  }),
)

const resourceOptions = computed<SelectOption<Resource, number>[]>(() =>
  (resourcesState.value?.data?.items ?? []).map((r) => ({
    raw: r,
    value: r.id,
    label: r.name,
    description: r.category,
  })),
)

// ─── Submit ──────────────────────────────────────────────────────────
const submit = handleSubmit(async (values) => {
  const body = {
    resourceId: values.resourceId!,
    maxUsage: values.maxUsage,
    description: values.description?.trim() || undefined,
  }
  try {
    if (mode === 'create') {
      await createConstraint({
        path: { project_id: currentProjectId.value! },
        body,
      })
      notifySuccess({ title: '已创建资源限制' })
    } else {
      await updateConstraint({
        path: { project_id: currentProjectId.value!, id: initialValues!.id },
        body,
      })
      notifySuccess({ title: '已保存资源限制' })
    }
    emit('saved')
  } catch (error) {
    notifyError({
      title: mode === 'create' ? '创建失败' : '保存失败',
      description: formatHttpError(error, '请稍后重试'),
    })
    console.error('Failed to save constraint:', error)
  }
})
</script>

<template>
  <form class="space-y-4" @submit.prevent="submit">
    <!-- 资源 -->
    <div class="fieldset">
      <label class="fieldset-label" for="constraint-resource">
        资源 <span class="text-error" aria-hidden="true">*</span>
      </label>
      <SearchableSelect
        id="constraint-resource"
        v-model:selected-value="resourceId"
        v-model:search="searchKeyword"
        v-bind="resourceIdAttrs"
        :options="resourceOptions"
        placeholder="选择资源"
        empty-text="未找到匹配资源"
        :loading="resourcesStatus === 'loading'"
        :disabled="isSubmitting || mode === 'edit'"
      />
      <span v-if="errors.resourceId" class="mt-1 text-xs text-error">
        {{ errors.resourceId }}
      </span>
    </div>

    <!-- 最大使用量 -->
    <div class="fieldset">
      <label class="fieldset-label" for="constraint-max-usage">最大使用量</label>
      <label
        class="input flex w-full items-center gap-2"
        :class="{ 'input-error': errors.maxUsage }"
      >
        <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
          trending_up
        </span>
        <input
          id="constraint-max-usage"
          :value="maxUsage ?? ''"
          v-bind="maxUsageAttrs"
          :disabled="isSubmitting"
          class="w-full bg-transparent outline-none"
          type="number"
          min="0"
          step="0.01"
          placeholder="输入最大使用量"
          @input="(e) => (maxUsage = (e.target as HTMLInputElement).valueAsNumber || undefined)"
        />
      </label>
      <span v-if="errors.maxUsage" class="mt-1 text-xs text-error">
        {{ errors.maxUsage }}
      </span>
    </div>

    <!-- 备注 -->
    <div class="fieldset">
      <label class="fieldset-label" for="constraint-description">备注</label>
      <textarea
        id="constraint-description"
        v-model="description"
        v-bind="descriptionAttrs"
        :disabled="isSubmitting"
        rows="3"
        placeholder="输入备注信息（可选，最多 500 字）"
        class="textarea w-full"
        :class="{ 'textarea-error': errors.description }"
      />
      <span v-if="errors.description" class="mt-1 text-xs text-error">
        {{ errors.description }}
      </span>
    </div>

    <!-- 操作栏 -->
    <div class="flex justify-end gap-2 pt-2 border-t border-base-content/10">
      <button
        type="button"
        class="btn btn-ghost btn-sm px-4"
        :disabled="isSubmitting"
        @click="emit('cancel')"
      >
        取消
      </button>
      <button
        type="submit"
        class="btn btn-primary btn-sm px-5"
        :disabled="isSubmitting || !isValid || !isDirty"
      >
        <span v-if="isSubmitting" class="loading loading-spinner loading-xs" aria-hidden="true" />
        {{ mode === 'edit' ? '保存' : '创建' }}
      </button>
    </div>
  </form>
</template>
