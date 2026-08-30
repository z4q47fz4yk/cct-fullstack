<script setup lang="ts">
import { ref } from 'vue'
import type { RunConfig } from '@/client/types.gen'

const config = defineModel<RunConfig>('config', { required: true })
const { collapsed = false, disabled } = defineProps<{
  collapsed?: boolean
  disabled?: boolean
}>()

const collapsedState = ref(collapsed ?? false)

function updateField<K extends keyof RunConfig>(key: K, value: RunConfig[K]) {
  config.value = { ...config.value, [key]: value }
}

const fields = [
  { key: 'popSize' as const, label: '种群大小', placeholder: '50', desc: '每代个体数量' },
  { key: 'maxGen' as const, label: '最大代数', placeholder: '100', desc: '迭代次数上限' },
  { key: 'irr' as const, label: '名义年利率', placeholder: '0.05', desc: '折现率，影响成本现值' },
  {
    key: 'acceleratedRatio' as const,
    label: '加速工期比例',
    placeholder: '0.8',
    desc: '加速施工时工期乘以此比例',
  },
  {
    key: 'maxOffset' as const,
    label: '最大偏移天数',
    placeholder: '3',
    desc: '任务开始时间最大偏移（天）',
  },
] as const
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
            :class="{ 'input-disabled': disabled }"
          >
            <input
              type="number"
              class="w-full bg-transparent outline-none"
              :placeholder="field.placeholder"
              :disabled="disabled"
              :value="config[field.key]"
              @input="updateField(field.key, Number(($event.target as HTMLInputElement).value))"
            />
          </label>
          <p class="fieldset-label text-fg-subtle">{{ field.desc }}</p>
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
