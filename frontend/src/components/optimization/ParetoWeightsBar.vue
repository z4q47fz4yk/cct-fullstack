<script setup lang="ts">
/**
 * 帕累托解排序权重栏
 *
 * - 标题行：当前权重（含指标名，与 chip tooltip 格式一致）
 * - chip 行：所有预设 + 末尾行内胶囊 `+自定义`
 * - 没有内联编辑；调整权重通过 `+自定义` 弹窗内的三列输入框
 * - 修改预设 = 删除 + 重新创建
 * - 列表顺序由父组件响应式更新，本组件无预览区
 */
import {
  WEIGHT_FIELDS,
  type NamedWeightPreset,
  type ParetoWeights,
  type WeightPreset,
} from '@/types/paretoWeights'

const weights = defineModel<ParetoWeights>('weights', { required: true })

const {
  presets = [],
  customPresets = [],
  bare = false,
} = defineProps<{
  /** 内置预设按钮（不可删除） */
  presets?: readonly WeightPreset[]
  /** 用户自定义预设按钮（可删除） */
  customPresets?: readonly NamedWeightPreset[]
  /** 无 panel 包裹（作为表格内 filter 工具条使用） */
  bare?: boolean
}>()

const emit = defineEmits<{
  'add-preset': []
  'remove-preset': [id: string, label: string]
}>()

/** 权重是否与当前权重完全一致（用于 chip 高亮） */
function matches(values: ParetoWeights): boolean {
  return (
    values.duration === weights.value.duration &&
    values.cost === weights.value.cost &&
    values.emission === weights.value.emission
  )
}

function presetTitle(values: ParetoWeights): string {
  return `工期 ${values.duration} / 成本 ${values.cost} / 碳排放 ${values.emission}`
}
</script>

<template>
  <div :class="bare ? '' : 'panel px-4 py-3'">
    <!-- 标题行 -->
    <h3 class="text-sm font-semibold text-base-content">
      排序权重:
      <template v-for="(field, i) in WEIGHT_FIELDS" :key="field.key">
        <span v-if="i" class="text-fg-muted mx-1">/</span>
        <span class="font-num font-normal">{{ field.label }} {{ weights[field.key] }}</span>
      </template>
    </h3>

    <!-- chip 区（内置 + 自定义 + 行内 +自定义 胶囊） -->
    <TransitionGroup
      v-if="presets.length > 0 || customPresets.length > 0"
      name="flip"
      tag="div"
      class="flex flex-wrap gap-2 mt-2"
    >
      <!-- 内置预设 -->
      <button
        v-for="preset in presets"
        :key="preset.label"
        type="button"
        class="h-7 px-3 rounded-full border text-[11px] transition-colors"
        :class="
          matches(preset.values)
            ? 'bg-primary/15 border-primary/40 text-primary'
            : 'bg-base-200/40 border-base-content/20 text-fg-muted hover:border-primary/40 hover:text-base-content'
        "
        :title="presetTitle(preset.values)"
        @click="weights = { ...preset.values }"
      >
        {{ preset.label }}
      </button>

      <!-- 用户自定义预设（label + 删除按钮并排） -->
      <div
        v-for="preset in customPresets"
        :key="preset.id"
        class="flex items-center h-7 pl-3 pr-1 rounded-full border text-[11px] transition-colors max-w-48"
        :class="
          matches(preset.values)
            ? 'bg-primary/25 border-primary/50 text-base-content'
            : 'bg-primary/10 border-primary/30 text-primary hover:bg-primary/15'
        "
      >
        <button
          type="button"
          class="truncate"
          :title="presetTitle(preset.values)"
          @click="weights = { ...preset.values }"
        >
          {{ preset.label }}
        </button>
        <button
          type="button"
          class="w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-base-content/40 hover:text-error hover:bg-error/10"
          :aria-label="`删除预设 ${preset.label}`"
          @click="emit('remove-preset', preset.id, preset.label)"
        >
          <span class="material-symbols-outlined text-sm">close</span>
        </button>
      </div>

      <!-- +自定义 虚线胶囊（样式同 chip，仅边框虚线） -->
      <button
        key="add-preset"
        type="button"
        class="inline-flex items-center gap-1 h-7 px-3 rounded-full border border-dashed text-[11px] transition-colors bg-base-200/40 border-base-content/20 text-fg-muted hover:border-primary/40 hover:text-base-content"
        @click="emit('add-preset')"
      >
        <span class="material-symbols-outlined text-xs">add</span>
        自定义
      </button>
    </TransitionGroup>
  </div>
</template>
