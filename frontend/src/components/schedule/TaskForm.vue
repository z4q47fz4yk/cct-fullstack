<script setup lang="ts">
import type { TaskCreate, TaskUpdate, TaskResp } from '@/client'
import { computed, ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import { vTaskCreate, vTaskUpdate } from '@/client/valibot.gen'

const { mode, initialData, isSubmitting, error } = defineProps<{
  mode: 'create' | 'edit'
  initialData?: TaskResp
  isSubmitting?: boolean
  error?: string | null
}>()

const emit = defineEmits<{
  submit: [data: TaskCreate | TaskUpdate]
  cancel: []
}>()

// 选择 schema
const validationSchema = computed(() => (mode === 'create' ? vTaskCreate : vTaskUpdate))

// 初始化表单
const { handleSubmit, resetForm, errors, setValues, meta, defineField } = useForm({
  validationSchema: toTypedSchema(validationSchema.value),
  initialValues: { name: '', duration: 1, code: '', description: '', completed: 0 },
})

const [name, nameAttrs] = defineField('name')
const [duration, durationAttrs] = defineField('duration')
const [code, codeAttrs] = defineField('code')
const [description, descriptionAttrs] = defineField('description')

// ──── 完成度：百分比输入 ↔ 0–1 小数 ─────────────────────────
// 后端 completed 语义为 0–1 小数；表单按百分比（0–100，可含小数）录入、
// 提交前转换，避免「输入 30 显示 3000%」的语义错位与浮点尾数。
// 录入页「当日工序进度」同样按百分比（0–100）录入（经 progress 接口的 percent 字段提交），
// 两处用户语义一致，仅本表单在提交 TaskCreate/TaskUpdate 前做百分比 → 小数转换。
const completedPct = ref<string | number>('')

/** 0–1 小数 → 百分比显示值（保留 2 位小数，消除浮点尾数，如 0.3 → 30） */
function toPercentInput(completed: number | null | undefined): number {
  return Math.round((completed ?? 0) * 10000) / 100
}

/** 百分比 → 0–1 小数（保留 4 位小数，消除浮点尾数，如 30 → 0.3） */
function toCompletedValue(pct: number): number {
  return Math.round(pct * 100) / 10000
}

/** 非法输入的可见提示（不只靠保存按钮禁用） */
const completedPctError = computed(() => {
  if (mode !== 'edit') return ''
  const raw = completedPct.value
  if (raw === '') return '请输入 0–100 之间的数字'
  const n = Number(raw)
  if (!Number.isFinite(n)) return '请输入 0–100 之间的数字'
  if (n < 0 || n > 100) return '完成度需在 0–100 之间'
  return ''
})

// 编辑模式初始化
watch(
  () => initialData,
  (data) => {
    if (data && mode === 'edit') {
      setValues(data)
      completedPct.value = toPercentInput(data.completed)
    }
  },
  { immediate: true },
)

// 提交处理
const onSubmit = handleSubmit((values) => {
  // 完成度按百分比录入（0–100），提交前转换为 0–1 小数
  if (completedPctError.value) return
  const pct = Number(completedPct.value)
  const completed = toCompletedValue(pct)

  if (mode === 'edit' && initialData) {
    // 只发送变化的字段
    const updateData: TaskUpdate = {}
    if (values.code !== initialData.code) updateData.code = values.code
    if (values.name !== initialData.name) updateData.name = values.name
    if (values.description !== initialData.description) updateData.description = values.description
    if (values.duration !== initialData.duration) updateData.duration = values.duration
    if (pct !== toPercentInput(initialData.completed)) updateData.completed = completed
    emit('submit', updateData)
  } else {
    emit('submit', values as TaskCreate)
  }
})

// 取消
function handleCancel() {
  resetForm()
  completedPct.value = ''
  emit('cancel')
}
</script>

<template>
  <form class="space-y-4" @submit.prevent="onSubmit">
    <div class="grid grid-cols-2 gap-4">
      <!-- 任务编码 -->
      <fieldset class="fieldset col-span-2">
        <legend class="fieldset-legend">任务编码</legend>
        <input
          v-model="code"
          v-bind="codeAttrs"
          :disabled="isSubmitting"
          class="input w-full"
          placeholder="如：TC-001（可选）"
          type="text"
        />
      </fieldset>

      <!-- 任务名称 -->
      <fieldset class="fieldset col-span-2">
        <legend class="fieldset-legend">任务名称</legend>
        <input
          v-model="name"
          v-bind="nameAttrs"
          :disabled="isSubmitting"
          class="input w-full"
          :class="{ 'input-error': errors.name }"
          placeholder="输入任务名称"
          type="text"
        />
        <span v-if="errors.name" class="text-xs text-error mt-1">
          {{ errors.name }}
        </span>
      </fieldset>

      <!-- 工期 -->
      <fieldset class="fieldset">
        <legend class="fieldset-legend">工期</legend>
        <label class="input w-full">
          <input
            v-model.number="duration"
            v-bind="durationAttrs"
            :disabled="isSubmitting"
            class="w-full"
            :class="{ 'input-error': errors.duration }"
            min="0.5"
            placeholder="0.5"
            step="0.5"
            type="number"
          />
          <span>天</span>
        </label>
        <span v-if="errors.duration" class="text-xs text-error mt-1">
          {{ errors.duration }}
        </span>
      </fieldset>

      <!-- 完成度 - 仅在编辑模式显示（按百分比 0–100 输入，提交时转 0–1 小数） -->
      <fieldset v-if="mode === 'edit'" class="fieldset">
        <legend class="fieldset-legend">完成度</legend>
        <label class="input w-full">
          <input
            v-model="completedPct"
            :disabled="isSubmitting"
            class="w-full"
            :class="{ 'input-error': completedPctError }"
            min="0"
            max="100"
            placeholder="0-100"
            step="any"
            type="number"
          />
          <span>%</span>
        </label>
        <span v-if="completedPctError" class="text-xs text-error mt-1">
          {{ completedPctError }}
        </span>
      </fieldset>

      <!-- 任务描述 -->
      <fieldset class="fieldset col-span-2">
        <legend class="fieldset-legend">任务描述</legend>
        <textarea
          v-model="description"
          v-bind="descriptionAttrs"
          :disabled="isSubmitting"
          class="textarea w-full"
          placeholder="输入任务描述（可选）"
          rows="3"
        />
      </fieldset>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="alert alert-error alert-sm">
      <span class="material-symbols-outlined icon-sm">error</span>
      <span class="text-sm">{{ error }}</span>
    </div>

    <!-- 操作按钮 -->
    <div class="modal-action">
      <button :disabled="isSubmitting" class="btn btn-ghost" type="button" @click="handleCancel">
        取消
      </button>
      <button
        :disabled="isSubmitting || !meta.valid || !!completedPctError"
        class="btn btn-primary"
        type="submit"
      >
        <span v-if="isSubmitting" class="loading loading-spinner loading-xs"></span>
        <span>{{ mode === 'edit' ? '保存' : '创建' }}</span>
      </button>
    </div>
  </form>
</template>
