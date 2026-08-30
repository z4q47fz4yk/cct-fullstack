<script setup lang="ts">
import type { TaskWithTagsResp } from '@/client/types.gen'
import { getSliceColor } from '@/utils/themeColors'
import TableEmptyState from '@/components/common/TableEmptyState.vue'

const { tasks, deletingId } = defineProps<{
  tasks: TaskWithTagsResp[]
  deletingId?: number | null
}>()

const emit = defineEmits<{
  (e: 'edit', task: TaskWithTagsResp): void
  (e: 'delete', task: TaskWithTagsResp): void
  (e: 'addPredecessor', task: TaskWithTagsResp): void
  (e: 'managePredecessors', task: TaskWithTagsResp): void
  (e: 'tags', task: TaskWithTagsResp): void
}>()

const tableHeaders = [
  { key: 'code', label: '任务编码', width: 'w-24' },
  { key: 'name', label: '任务名称', width: 'w-48' },
  { key: 'tags', label: '标签', width: 'w-52' },
  { key: 'description', label: '任务说明', width: 'flex-1' },
  { key: 'duration', label: '工期(天)', width: 'w-20', num: true },
  { key: 'predecessors', label: '前置任务', width: 'w-44' },
  { key: 'actions', label: '操作', width: 'w-36' },
]

/** 每行最多展示的标签 chip 数，其余折叠为 +N */
const MAX_TAGS_VISIBLE = 2

/** 前置任务列：每行最多展示的编码 chip 数 */
const MAX_PREDECESSORS_VISIBLE = 2

function visibleTags(task: TaskWithTagsResp) {
  return (task.tags ?? []).slice(0, MAX_TAGS_VISIBLE)
}

function hiddenTagCount(task: TaskWithTagsResp): number {
  return Math.max(0, (task.tags?.length ?? 0) - MAX_TAGS_VISIBLE)
}

function tagListText(task: TaskWithTagsResp): string {
  return (task.tags ?? []).map((t) => t.name).join('、')
}

function visiblePredecessors(task: TaskWithTagsResp) {
  return (task.predecessors ?? []).slice(0, MAX_PREDECESSORS_VISIBLE)
}

function hiddenPredecessorCount(task: TaskWithTagsResp): number {
  return Math.max(0, (task.predecessors?.length ?? 0) - MAX_PREDECESSORS_VISIBLE)
}

function predecessorListText(task: TaskWithTagsResp): string {
  return (task.predecessors ?? []).map((p) => `${p.code} ${p.name}`).join('、')
}

function truncateDescription(desc: string, maxLength: number = 50): string {
  if (!desc) return ''
  return desc.length > maxLength ? desc.slice(0, maxLength) + '...' : desc
}
</script>

<template>
  <div class="overflow-x-auto">
    <table class="table">
      <thead>
        <tr class="">
          <th
            v-for="header in tableHeaders"
            :key="header.key"
            :class="[header.width, 'whitespace-nowrap', header.num ? 'table-num' : '']"
          >
            {{ header.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-if="tasks.length > 0">
          <tr v-for="task in tasks" :key="task.id" class="hover:bg-base-300/30 transition-colors">
            <!-- 任务编码 -->
            <td>
              <span
                class="badge badge-primary badge-sm text-nowrap"
                :class="{ 'badge-error': task.isCritical }"
              >
                {{ task.code }}
              </span>
            </td>

            <!-- 任务名称 -->
            <td>
              <div
                class="font-medium text-base-content truncate max-w-45"
                :class="{ 'text-error': task.isCritical }"
                :title="task.name"
              >
                {{ task.name }}
              </div>
            </td>

            <!-- 标签 -->
            <td>
              <!-- 标签列：经典胶囊样式，超限折叠为 +N，悬浮查看全量 -->
              <div
                v-if="task.tags && task.tags.length > 0"
                class="flex items-center gap-1 overflow-hidden"
                :title="tagListText(task)"
              >
                <span
                  v-for="(tag, index) in visibleTags(task)"
                  :key="tag.id"
                  class="inline-flex items-center gap-1 h-5 px-1.5 rounded-full border text-[10px] whitespace-nowrap shrink-0"
                  :style="{
                    backgroundColor: `${getSliceColor(index)}14`,
                    borderColor: `${getSliceColor(index)}3d`,
                  }"
                >
                  <span
                    class="w-1.5 h-1.5 rounded-full shrink-0"
                    :style="{ backgroundColor: getSliceColor(index) }"
                  ></span>
                  <span class="text-fg-muted">{{ tag.name }}</span>
                </span>
                <span
                  v-if="hiddenTagCount(task) > 0"
                  class="inline-flex items-center h-5 px-1.5 rounded-full border border-base-content/20 bg-base-200/60 text-[10px] font-mono text-fg-subtle whitespace-nowrap shrink-0"
                >
                  +{{ hiddenTagCount(task) }}
                </span>
              </div>
              <span v-else class="text-xs text-fg-subtle">未打标</span>
            </td>

            <!-- 任务说明 -->
            <td>
              <div
                v-if="task.description"
                class="text-sm text-base-content/70 truncate max-w-75"
                :title="task.description"
              >
                {{ truncateDescription(task.description, 60) }}
              </div>
              <span v-else class="text-sm text-neutral-content italic">-</span>
            </td>

            <!-- 工期 -->
            <td class="table-num">
              <span class="font-num font-medium">{{ task.duration }}</span>
            </td>

            <!-- 前置任务 -->
            <td>
              <div
                v-if="task.predecessors && task.predecessors.length > 0"
                class="flex items-center gap-1 overflow-hidden"
                :title="predecessorListText(task)"
              >
                <span
                  v-for="(p, index) in visiblePredecessors(task)"
                  :key="p.id"
                  class="inline-flex items-center h-5 px-1.5 rounded-md border text-[10px] font-num whitespace-nowrap shrink-0"
                  :style="{
                    backgroundColor: `${getSliceColor(index)}14`,
                    borderColor: `${getSliceColor(index)}3d`,
                    color: getSliceColor(index),
                  }"
                >
                  {{ p.code }}
                </span>
                <span
                  v-if="hiddenPredecessorCount(task) > 0"
                  class="inline-flex items-center h-5 px-1.5 rounded-md border border-base-content/20 bg-base-200/60 text-[10px] font-num text-fg-subtle whitespace-nowrap shrink-0"
                >
                  +{{ hiddenPredecessorCount(task) }}
                </span>
                <button
                  type="button"
                  class="btn btn-ghost btn-xs btn-square shrink-0 ml-0.5"
                  :title="`管理前置任务 (${task.predecessors.length})`"
                  :aria-label="`管理前置任务，共 ${task.predecessors.length} 个`"
                  @click="emit('managePredecessors', task)"
                >
                  <span class="material-symbols-outlined icon-sm">tune</span>
                </button>
              </div>
              <button
                v-else
                type="button"
                class="btn btn-ghost btn-xs gap-1 text-fg-subtle"
                title="添加前置任务"
                @click="emit('addPredecessor', task)"
              >
                <span class="material-symbols-outlined icon-sm">add_link</span>
                <span>添加</span>
              </button>
            </td>

            <!-- 操作 -->
            <td>
              <div class="flex items-center gap-1">
                <button
                  class="btn btn-ghost btn-sm btn-square"
                  title="为任务打标"
                  @click="emit('tags', task)"
                >
                  <span class="material-symbols-outlined icon-sm">label</span>
                </button>
                <button
                  class="btn btn-ghost btn-sm btn-square"
                  title="编辑"
                  @click="emit('edit', task)"
                >
                  <span class="material-symbols-outlined icon-sm">edit</span>
                </button>
                <button
                  class="btn btn-ghost btn-sm btn-square text-error hover:bg-error/10"
                  :disabled="deletingId === task.id"
                  :aria-label="deletingId === task.id ? '正在删除...' : `删除任务 ${task.name}`"
                  title="删除"
                  @click="emit('delete', task)"
                >
                  <span v-if="deletingId === task.id" class="loading loading-spinner loading-xs" />
                  <span v-else class="material-symbols-outlined icon-sm">delete</span>
                </button>
              </div>
            </td>
          </tr>
        </template>

        <!-- 空状态 -->
        <TableEmptyState
          v-else
          :colspan="tableHeaders.length"
          title="暂无任务"
          description="点击添加按钮创建第一个任务"
          icon="task_alt"
        />
      </tbody>
    </table>
  </div>
</template>
