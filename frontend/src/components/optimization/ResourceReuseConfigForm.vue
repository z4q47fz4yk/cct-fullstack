<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useForm, useIsFormDirty, useIsFormValid } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import * as v from 'valibot'
import { vResourceReuseConfigCreate } from '@/client/valibot.gen'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useReuseConfigApi } from '@/composables/useReuseConfigApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useToast } from '@/composables/useToast'
import SearchableSelect from '@/components/common/SearchableSelect.vue'
import type { ResourceReuseConfigResp } from '@/types/reuseConfig'
import type { Resource } from '@/types/resource'
import type { SelectOption } from '@/types/select'
import type { ResourceReuseConfigCreate } from '@/client'

const { mode = 'create', initialValues = null } = defineProps<{
  mode?: 'create' | 'edit'
  initialValues?: ResourceReuseConfigResp | null
}>()

const emit = defineEmits<{
  (e: 'saved'): void
  (e: 'cancel'): void
}>()

const { createConfig, updateConfig } = useReuseConfigApi()
const { currentProjectId } = useProjectContext()
const { notifyError, notifySuccess } = useToast()

// ─── Schema ──────────────────────────────────────────────────────────
// resourceId 允许 null（SearchableSelect 未选时为 null，isValid 自然为 false）
const createSchema = toTypedSchema(vResourceReuseConfigCreate)

// edit 模式不含 resourceId（提交时由父组件的 editingItem.id 保证）；只定义结构，i18n 由全局 @valibot/i18n/zh-CN 处理
const editSchema = toTypedSchema(
  v.partial(vResourceReuseConfigCreate),
  // v.object({
  //   resourceId: v.optional(v.pipe(v.number(), v.integer())),
  //   maxReuses: v.pipe(v.number(), v.integer(), v.minValue(1)),
  //   reuseCount: v.pipe(v.number(), v.integer(), v.minValue(1)),
  //   affectCost: v.boolean(),
  //   description: v.nullish(v.pipe(v.string(), v.maxLength(500))),
  // }),
)

const formSchema = computed(() => (mode === 'create' ? createSchema : editSchema))

// ─── Form ────────────────────────────────────────────────────────────
function computeDefaults() {
  if (mode === 'edit' && initialValues) {
    return initialValues
  }
  return {
    resourceId: null,
    maxReuses: 1,
    reuseCount: 1,
    affectCost: false,
    description: '',
  } as unknown as ResourceReuseConfigCreate // 有 valibot 进行验证，不会造成运行时错误
}

const { handleSubmit, errors, defineField, resetForm, isSubmitting, meta } = useForm({
  validationSchema: formSchema.value,
  initialValues: computeDefaults(),
})

const isDirty = useIsFormDirty()
const isValid = useIsFormValid()

const [resourceId, resourceIdAttrs] = defineField('resourceId')
const [maxReuses, maxReusesAttrs] = defineField('maxReuses')
const [reuseCount, reuseCountAttrs] = defineField('reuseCount')
const [affectCost, affectCostAttrs] = defineField('affectCost')
const [description, descriptionAttrs] = defineField('description')

// props 变化时重新同步表单（用户编辑不同行时）
watch(
  () => [mode, initialValues?.id] as const,
  () => resetForm({ values: computeDefaults() }),
)

// 软校验：实际周转次数超过最大周转次数时提示（不阻断提交，后端为准）
const reuseCountExceeds = computed(() => (reuseCount.value ?? 0) > (maxReuses.value ?? 0))

// ─── SearchableSelect ───────────────────────────────────────────────
const searchKeyword = ref('')

const { state: resourcesState, asyncStatus: resourcesStatus } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { category: 'material', name: searchKeyword.value || undefined },
  }),
)

const materialOptions = computed<SelectOption<Resource, number>[]>(() =>
  (resourcesState.value?.data?.items ?? []).map((r) => ({
    raw: r,
    value: r.id,
    label: r.name,
  })),
)

// ─── Submit ──────────────────────────────────────────────────────────
const submit = handleSubmit(async (values) => {
  if (mode === 'create') {
    await createConfig({
      path: { project_id: currentProjectId.value! },
      body: {
        resourceId: values.resourceId!,
        maxReuses: values.maxReuses,
        reuseCount: values.reuseCount,
        affectCost: values.affectCost,
        description: values.description?.trim() || undefined,
      },
    })
    notifySuccess({ title: '已创建可复用材料配置' })
  } else {
    await updateConfig({
      path: { project_id: currentProjectId.value!, id: initialValues!.id },
      body: {
        maxReuses: values.maxReuses,
        reuseCount: values.reuseCount,
        affectCost: values.affectCost,
        description: values.description?.trim() || null,
      },
    })
    notifySuccess({ title: '已保存可复用材料配置' })
  }
  emit('saved')
})
</script>

<template>
  <form class="space-y-4 grid xl:grid-cols-2 gap-4" @submit.prevent="submit">
    <!-- 材料 -->
    <div class="fieldset">
      <label class="fieldset-label" for="reuse-resource">
        材料 <span class="text-error" aria-hidden="true">*</span>
      </label>
      <SearchableSelect
        id="reuse-resource"
        v-model:selected-value="resourceId"
        v-model:search="searchKeyword"
        v-bind="resourceIdAttrs"
        :options="materialOptions"
        placeholder="选择材料"
        empty-text="未找到匹配材料"
        :loading="resourcesStatus === 'loading'"
        :disabled="isSubmitting || mode === 'edit'"
      />
      <span v-if="errors.resourceId" class="mt-1 text-xs text-error">
        {{ errors.resourceId }}
      </span>
    </div>

    <!-- 是否影响成本 -->
    <div class="fieldset">
      <span class="fieldset-label">是否影响成本</span>
      <input
        v-model="affectCost"
        v-bind="affectCostAttrs as any"
        :disabled="isSubmitting"
        class="sr-only"
        type="checkbox"
        tabindex="-1"
        aria-hidden="true"
      />
      <div
        class="flex w-full gap-1 rounded-field border border-base-content/10 bg-base-content/5 p-[0.1rem] shadow-inner"
        role="group"
        aria-label="是否影响成本"
      >
        <button
          type="button"
          class="flex-1 rounded-field px-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          :class="
            affectCost
              ? 'bg-primary/15 text-primary shadow-sm'
              : 'text-fg-muted hover:bg-base-content/5 hover:text-base-content'
          "
          :disabled="isSubmitting"
          :aria-pressed="affectCost"
          @click="affectCost = true"
        >
          周转摊薄成本
        </button>
        <button
          type="button"
          class="min-h-[2.4rem] flex-1 rounded-field px-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          :class="
            !affectCost
              ? 'bg-primary/15 text-primary shadow-sm'
              : 'text-fg-muted hover:bg-base-content/5 hover:text-base-content'
          "
          :disabled="isSubmitting"
          :aria-pressed="!affectCost"
          @click="affectCost = false"
        >
          仅摊薄碳排放
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
      <!-- 最大周转次数 -->
      <div class="fieldset">
        <label class="fieldset-label" for="reuse-max">最大周转次数</label>
        <label
          class="input flex w-full items-center gap-2"
          :class="{ 'input-error': errors.maxReuses }"
        >
          <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
            autorenew
          </span>
          <input
            id="reuse-max"
            :value="maxReuses ?? ''"
            v-bind="maxReusesAttrs"
            :disabled="isSubmitting"
            class="w-full bg-transparent outline-none"
            type="number"
            min="1"
            step="1"
            placeholder="理论最大周转次数"
            @input="(e) => (maxReuses = (e.target as HTMLInputElement).valueAsNumber || undefined)"
          />
        </label>
        <span v-if="errors.maxReuses" class="mt-1 text-xs text-error">
          {{ errors.maxReuses }}
        </span>
      </div>

      <!-- 实际周转次数 -->
      <div class="fieldset">
        <label class="fieldset-label" for="reuse-count">实际周转次数</label>
        <label
          class="input flex w-full items-center gap-2"
          :class="{ 'input-error': errors.reuseCount }"
        >
          <span class="material-symbols-outlined icon-sm text-primary/70" aria-hidden="true">
            repeat
          </span>
          <input
            id="reuse-count"
            :value="reuseCount ?? ''"
            v-bind="reuseCountAttrs"
            :disabled="isSubmitting"
            class="w-full bg-transparent outline-none"
            type="number"
            min="1"
            step="1"
            placeholder="本项目实际周转次数"
            @input="(e) => (reuseCount = (e.target as HTMLInputElement).valueAsNumber || undefined)"
          />
        </label>
        <p v-if="reuseCountExceeds" class="mt-1 text-xs text-warning">
          实际周转次数已超过最大周转次数，请确认
        </p>
        <span v-if="errors.reuseCount" class="mt-1 text-xs text-error">
          {{ errors.reuseCount }}
        </span>
      </div>
    </div>

    <!-- 备注 -->
    <div class="fieldset">
      <label class="fieldset-label" for="reuse-description">备注</label>
      <textarea
        id="reuse-description"
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
    <div class="xl:col-span-2 flex justify-end gap-2 pt-2 border-t border-base-content/10">
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
        :disabled="isSubmitting || !meta.touched || !isValid || !isDirty"
      >
        <span v-if="isSubmitting" class="loading loading-spinner loading-xs" aria-hidden="true" />
        {{ mode === 'edit' ? '保存' : '创建' }}
      </button>
    </div>
  </form>
</template>
