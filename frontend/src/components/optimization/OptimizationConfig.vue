<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RunConfig } from '@/client/types.gen'
import { RUN_CONFIG_RULES, validateRunConfigField, type RunConfigKey } from '@/utils/runConfig'

const config = defineModel<RunConfig>('config', { required: true })
const { collapsed = false, disabled } = defineProps<{
  collapsed?: boolean
  disabled?: boolean
}>()

const collapsedState = ref(collapsed ?? false)

function updateField(key: RunConfigKey, value: number | undefined) {
  config.value = { ...config.value, [key]: value }
}

/** 空输入视为未填写（undefined），其余转数字（非法取值由字段校验提示兜底） */
function parseInput(raw: string): number | undefined {
  if (raw.trim() === '') return undefined
  return Number(raw)
}

interface FieldMeta {
  key: RunConfigKey
  label: string
  placeholder: string
  desc: string
}

const fields: ReadonlyArray<FieldMeta> = [
  { key: 'popSize', label: '种群大小', placeholder: '50', desc: '每代个体数量' },
  { key: 'maxGen', label: '最大代数', placeholder: '100', desc: '迭代次数上限' },
  { key: 'irr', label: '名义年利率', placeholder: '0.05', desc: '折现率，影响成本现值' },
  {
    key: 'acceleratedRatio',
    label: '加速工期比例',
    placeholder: '0.8',
    desc: '加速施工时工期乘以此比例',
  },
  {
    key: 'maxOffset',
    label: '最大偏移天数',
    placeholder: '3',
    desc: '任务开始时间最大偏移（天）',
  },
]

/** 字段级校验错误（随输入实时提示），null/缺省 = 通过 */
const fieldErrors = computed<Partial<Record<RunConfigKey, string>>>(() => {
  const out: Partial<Record<RunConfigKey, string>> = {}
  for (const f of fields) {
    const message = validateRunConfigField(f.key, config.value[f.key])
    if (message) out[f.key] = message
  }
  return out
})
</script>

<template>
  <div>
    <!-- 配置表单 -->
    <div v-show="!collapsed" class="space-y-4">
      <div class="grid grid-cols-2 xl:grid-cols-3 gap-4">
        <fieldset v-for="field in fields" :key="field.key" class="fieldset">
          <legend class="fieldset-label">{{ field.label }}</legend>
          <label
            class="input flex w-full items-center gap-2"
            :class="{
              'input-disabled': disabled,
              'input-error': !!fieldErrors[field.key] && !disabled,
            }"
          >
            <input
              type="number"
              class="w-full bg-transparent outline-none"
              :placeholder="field.placeholder"
              :disabled="disabled"
              :min="RUN_CONFIG_RULES[field.key].min"
              :max="RUN_CONFIG_RULES[field.key].max"
              :step="RUN_CONFIG_RULES[field.key].step"
              :value="config[field.key]"
              @input="updateField(field.key, parseInput(($event.target as HTMLInputElement).value))"
            />
          </label>
          <p class="fieldset-label text-fg-subtle">{{ field.desc }}</p>
          <p v-if="fieldErrors[field.key] && !disabled" class="text-xs text-error mt-0.5">
            {{ fieldErrors[field.key] }}
          </p>
        </fieldset>
      </div>

      <!-- 运行中提示 -->
      <div v-if="disabled" class="flex items-center gap-2 text-sm text-fg-muted">
        <span class="material-symbols-outlined icon-sm">lock</span>
        优化运行中，配置已锁定
      </div>
    </div>
  </div>
</template>
