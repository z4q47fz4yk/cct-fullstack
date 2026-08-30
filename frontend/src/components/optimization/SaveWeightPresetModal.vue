<script setup lang="ts">
/**
 * 保存自定义权重预设弹窗
 *
 * - 三列输入框（工期 / 成本 / 碳排放），在局部副本上编辑，不写入 store
 * - 名称输入框：1~20 字符（valibot i18n 全局中文）
 * - 点「保存」时 emit 名称 + 编辑后的权重，由父组件持久化
 * - 同名冲突由父组件捕获 addCustomPreset 返回 false 后注入 externalError
 *
 * 弹窗打开时以 props.weights 重置局部副本；取消/关闭不影响 store。
 */
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import * as v from 'valibot'
import { computed, ref, watch } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { WEIGHT_FIELDS, type ParetoWeights } from '@/types/paretoWeights'

const props = defineProps<{
  open: boolean
  /** 弹窗打开时的初始权重 */
  weights: ParetoWeights
  externalError?: string | null
}>()

const emit = defineEmits<{
  'update:open': [v: boolean]
  confirm: [name: string, weights: ParetoWeights]
}>()

/** 局部权重副本：打开时从 props 重置，保存时提交 */
const draft = ref<ParetoWeights>({ ...props.weights })

const nameSchema = toTypedSchema(
  v.object({
    name: v.pipe(
      v.string('请输入名称'),
      v.trim(),
      v.minLength(1, '请输入名称'),
      v.maxLength(20, '名称不能超过 20 个字符'),
    ),
  }),
)

const { handleSubmit, errors, defineField, resetForm } = useForm({
  validationSchema: nameSchema,
  initialValues: { name: '' },
})

const [name, nameAttrs] = defineField('name')

// 弹窗打开时重置名称输入与权重副本
watch(
  () => props.open,
  (v) => {
    if (v) {
      resetForm({ values: { name: '' } })
      draft.value = { ...props.weights }
    }
  },
)

function updateWeight<K extends keyof ParetoWeights>(key: K, raw: string) {
  const parsed = Number.parseInt(raw, 10)
  const safe = Number.isNaN(parsed) ? 0 : Math.min(100, Math.max(0, parsed))
  draft.value = { ...draft.value, [key]: safe }
}

const submit = handleSubmit((values) => {
  emit('confirm', values.name.trim(), draft.value)
})

const showError = computed(() => !!props.externalError || !!errors.value.name)
const errorText = computed(() => props.externalError ?? errors.value.name ?? '')
</script>

<template>
  <BaseModal
    :open="open"
    title="保存自定义权重"
    class="max-w-md"
    @close="emit('update:open', false)"
    @update:open="emit('update:open', $event)"
  >
    <!-- 三列权重输入（局部副本，仅保存时生效） -->
    <div class="grid grid-cols-3 gap-3 mb-4">
      <fieldset v-for="field in WEIGHT_FIELDS" :key="field.key" class="fieldset">
        <legend class="fieldset-label">{{ field.label }}</legend>
        <label class="input flex w-full items-center gap-2">
          <input
            type="number"
            min="0"
            max="100"
            step="1"
            class="w-full bg-transparent outline-none font-num"
            :value="draft[field.key]"
            @input="updateWeight(field.key, ($event.target as HTMLInputElement).value)"
          />
        </label>
      </fieldset>
    </div>

    <!-- 名称输入 -->
    <form class="fieldset" @submit.prevent="submit">
      <label class="fieldset-label" for="preset-name">
        名称 <span class="text-error" aria-hidden="true">*</span>
      </label>
      <label class="input flex w-full items-center gap-2">
        <input
          id="preset-name"
          v-model="name"
          v-bind="nameAttrs"
          type="text"
          class="w-full bg-transparent outline-none"
          placeholder="例如：时间激进"
          maxlength="20"
          autocomplete="off"
        />
      </label>
      <p v-if="showError" class="mt-1 text-xs text-error" role="alert">
        {{ errorText }}
      </p>
      <p v-else class="fieldset-label text-fg-subtle">1~20 个字符</p>
    </form>

    <!-- 操作按钮 -->
    <template #actions>
      <button type="button" class="btn btn-ghost" @click="emit('update:open', false)">取消</button>
      <button type="button" class="btn btn-primary" @click="submit">保存</button>
    </template>
  </BaseModal>
</template>
