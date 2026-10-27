<script setup lang="ts">
/**
 * ReportSteps - 日报导入向导步骤条（设计稿 steps）
 *
 * 三步：导入日报 → 核对资源 → 分配工序。
 * 当前步 primary 高亮，已完成步绿色对勾，未开始步灰色。
 */
const { current } = defineProps<{
  /** 当前步骤（1-3） */
  current: 1 | 2 | 3
}>()

const STEPS = ['导入日报', '核对资源', '分配工序'] as const
</script>

<template>
  <div class="flex items-center justify-center mb-6 select-none" aria-label="导入进度">
    <template v-for="(label, i) in STEPS" :key="label">
      <div class="flex items-center gap-2" :class="i + 1 === current ? 'text-base-content' : ''">
        <span
          class="w-[26px] h-[26px] rounded-full flex items-center justify-center text-[13px] font-semibold shrink-0"
          :class="
            i + 1 < current
              ? 'bg-success text-success-content'
              : i + 1 === current
                ? 'bg-primary text-primary-content'
                : 'bg-base-300/60 text-fg-muted'
          "
        >
          <span v-if="i + 1 < current" class="material-symbols-outlined icon-sm">check</span>
          <template v-else>{{ i + 1 }}</template>
        </span>
        <span
          class="text-[13px] whitespace-nowrap"
          :class="
            i + 1 === current ? 'font-medium text-base-content' : 'text-fg-subtle'
          "
        >
          {{ label }}
        </span>
      </div>
      <span
        v-if="i < STEPS.length - 1"
        class="flex-1 h-0.5 min-w-6 mx-3 rounded"
        :class="i + 1 < current ? 'bg-success/60' : 'bg-base-300/70'"
      />
    </template>
  </div>
</template>
