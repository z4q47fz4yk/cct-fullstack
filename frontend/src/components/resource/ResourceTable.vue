<script setup lang="ts">
import { computed } from 'vue'
import type { Resource, ResourceCategory } from '@/types/resource'
import { categoryConfigMap } from '@/types/resource'
import type { ResourceWithConfigResp } from '@/client/types.gen'
import { fmtNumber } from '@/utils/format'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import TagInput from '@/components/tag/TagInput.vue'

const { resources, category } = defineProps<{
  /**
   * 当前页资源；每条已通过 listResources 的 include_* 选项附带
   * `tags` / `constraint` / `reuse_config` 字段，无需调用方额外注入 Map。
   */
  resources: ResourceWithConfigResp[]
  /** 当前分类（仅用于表格列的图标与按钮语义） */
  category: ResourceCategory
}>()

const emit = defineEmits<{
  (e: 'edit', resource: Resource): void
  (e: 'delete', resource: Resource): void
}>()

interface TableHeader {
  key: string
  label: string
  width: string
  /** 数字列：表头右对齐（body td 需另加 table-num） */
  num?: boolean
  /** 表头 colspan（隐式拆分列时用，如「数字列 + 单位列」） */
  colspan?: number
  /** 表头居中（覆盖 colspan 两列） */
  center?: boolean
}

const tableHeaders = computed<TableHeader[]>(() => {
  const headers: TableHeader[] = [
    // { key: 'select', label: '', width: 'w-12' },
    // { key: 'category', label: '类别', width: 'w-16' },
    { key: 'name', label: '资源名称', width: 'flex-1' },
    { key: 'config', label: '', width: 'w-16' },
    { key: 'tags', label: '标签', width: 'w-52' },
    // { key: 'id', label: 'ID', width: 'w-20' },
    // 单价/碳因子：表头 colspan=2 隐式拆为「数字列 + 单位列」，跨行数字对齐；
    // 表头居中（覆盖两列），数字与单位间收紧 padding 营造单列观感
    { key: 'unitPrice', label: '单价', width: 'w-40', colspan: 2, center: true },
    { key: 'carbonFactor', label: '碳排放因子', width: 'w-44', colspan: 2, center: true },
    { key: 'actions', label: '操作', width: 'w-28' },
  ]
  return headers
})

/** 物理单元格总数（含 colspan 拆出的隐式列） */
const cellCount = computed(() => tableHeaders.value.reduce((sum, h) => sum + (h.colspan ?? 1), 0))

const categoryIcon = computed(() => categoryConfigMap[category].icon)
</script>

<template>
  <div class="overflow-x-auto">
    <table class="table">
      <thead>
        <tr>
          <th
            v-for="header in tableHeaders"
            :key="header.key"
            :colspan="header.colspan"
            :class="[
              header.width,
              header.num ? 'table-num' : '',
              header.center ? 'text-center' : '',
            ]"
          >
            <template v-if="header.key === 'select'">
              <label class="label cursor-pointer justify-center">
                <input type="checkbox" class="checkbox checkbox-sm" disabled />
              </label>
            </template>
            <template v-else>
              {{ header.label }}
            </template>
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-if="resources.length > 0">
          <tr
            v-for="resource in resources"
            :key="resource.id"
            class="hover:bg-base-300/30 transition-colors"
          >
            <!-- <td class="text-center">
              <label class="label cursor-pointer justify-center">
                <input
                  type="checkbox"
                  class="checkbox checkbox-sm"
                  disabled
                  title="批量选择功能尚未实现"
                />
              </label>
            </td>
            <td class="text-center">
              <span
                class="material-symbols-outlined icon-md"
                :title="categoryConfigMap[category].label"
              >
                {{ categoryIcon }}
              </span>
            </td> -->
            <td>
              <div class="font-medium text-base-content">{{ resource.name }}</div>
            </td>
            <td class="w-16">
              <!-- 状态徽标：图标-only，无文字；title/aria 中文说明 -->
              <div class="flex items-center gap-1.5">
                <span
                  v-if="resource.constraint"
                  class="material-symbols-outlined icon-sm text-warning"
                  role="img"
                  :aria-label="`有限制：日用量上限 ${resource.constraint.maxUsage}`"
                  :title="`有限制：日用量上限 ${resource.constraint.maxUsage}`"
                >
                  rule
                </span>
                <span
                  v-if="resource.reuseConfig"
                  class="material-symbols-outlined icon-sm text-cyan"
                  role="img"
                  :aria-label="`可复用：周转 ${resource.reuseConfig.maxReuses} 次`"
                  :title="`可复用：周转 ${resource.reuseConfig.maxReuses} 次`"
                >
                  autorenew
                </span>
              </div>
            </td>
            <td>
              <!-- 标签列：行内 tag-input（悬停 ✕ 移除，(+tag) 虚线新增） -->
              <TagInput
                :entity="{ type: 'resource', id: resource.id }"
                :tags="resource.tags ?? []"
              />
            </td>
            <td class="table-num w-24 pr-1">
              <span class="font-num font-medium">{{ fmtNumber(resource.unitPrice, 2) }}</span>
            </td>
            <td class="w-20 pl-0">
              <span class="text-neutral-content text-sm">元/{{ resource.unit }}</span>
            </td>
            <td class="table-num w-24 pr-1">
              <span class="font-num">{{ fmtNumber(resource.carbonFactor, 2) }}</span>
            </td>
            <td class="w-24 pl-0">
              <span class="text-neutral-content text-sm text-nowrap">kg/{{ resource.unit }}</span>
            </td>
            <td>
              <div class="flex items-center gap-1">
                <button
                  class="btn btn-ghost btn-xs btn-square"
                  title="编辑"
                  @click="emit('edit', resource)"
                >
                  <span class="material-symbols-outlined icon-sm">edit</span>
                </button>
                <button
                  class="btn btn-ghost btn-xs btn-square text-error hover:bg-error/10"
                  title="删除"
                  @click="emit('delete', resource)"
                >
                  <span class="material-symbols-outlined icon-sm">delete</span>
                </button>
              </div>
            </td>
          </tr>
        </template>

        <!-- 空状态 -->
        <TableEmptyState
          v-else
          :colspan="cellCount"
          title="暂无资源"
          description="该分类下还没有添加资源"
          icon="inventory_2"
        />
      </tbody>
    </table>
  </div>
</template>
