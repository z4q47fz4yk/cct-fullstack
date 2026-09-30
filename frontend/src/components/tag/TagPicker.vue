<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TagResp } from '@/client/types.gen'
import { filterTags, groupTags } from '@/utils/tagGroup'

/**
 * 扁平标签多选器（按 group 分组展示）。
 * 用于资源/任务/用量打标弹窗与图表切片标签选择。
 */
const props = defineProps<{
  tags: TagResp[]
  modelValue: number[]
  search?: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [ids: number[]]
}>()

const localSearch = ref('')
const keyword = computed(() => props.search ?? localSearch.value)

const visibleTags = computed(() => filterTags(props.tags, keyword.value))
const groups = computed(() => groupTags(visibleTags.value))

// 区分两种空态：「项目确实没有可选标签」 vs「搜索无匹配」
const noSearchMatch = computed(
  () => props.tags.length > 0 && visibleTags.value.length === 0 && keyword.value.trim() !== '',
)

function isChecked(id: number): boolean {
  return props.modelValue.includes(id)
}

function toggle(id: number) {
  if (props.disabled) return
  const next = new Set(props.modelValue)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  // 保持原有顺序 + 新增追加末尾
  const ordered = props.modelValue.filter((x) => next.has(x))
  for (const x of next) if (!ordered.includes(x)) ordered.push(x)
  emit('update:modelValue', ordered)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <label class="input flex items-center gap-2">
      <span class="material-symbols-outlined icon-sm text-fg-subtle">search</span>
      <input
        v-model="localSearch"
        type="text"
        class="w-full bg-transparent"
        placeholder="搜索标签名称或分组…"
      />
    </label>

    <!-- 空态：区分「项目确实没有标签」与「搜索无匹配」 -->
    <div v-if="groups.length === 0" class="text-center py-6 text-xs text-fg-subtle">
      <template v-if="noSearchMatch">未找到匹配的标签，请调整搜索关键词</template>
      <template v-else>暂无标签，请先在「碳排放标签」中创建</template>
    </div>

    <div v-for="group in groups" :key="group.group" class="flex flex-col gap-0.5">
      <p
        class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-base-300/60 text-fg-muted inline-block self-start mb-0.5"
      >
        {{ group.label }} · {{ group.tags.length }}
      </p>
      <label
        v-for="tag in group.tags"
        :key="tag.id"
        class="flex items-center gap-2 px-2 h-9 rounded-lg cursor-pointer transition-colors hover:bg-base-300/40"
      >
        <input
          type="checkbox"
          class="checkbox checkbox-sm"
          :checked="isChecked(tag.id)"
          :disabled="disabled"
          @change="toggle(tag.id)"
        />
        <span
          class="text-sm truncate"
          :class="isChecked(tag.id) ? 'text-base-content font-medium' : 'text-fg-muted'"
        >
          {{ tag.name }}
        </span>
      </label>
    </div>
  </div>
</template>
