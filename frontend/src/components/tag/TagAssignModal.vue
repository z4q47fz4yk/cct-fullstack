<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useEntityTags, useEntityTagApi, type TagEntityRef } from '@/composables/useEntityTagApi'
import { useTagApi } from '@/composables/useTagApi'
import { useTagDimensionApi } from '@/composables/useTagDimensionApi'
import { formatHttpError } from '@/utils/error'
import { getSliceColor } from '@/utils/themeColors'
import type { TagResp } from '@/client/types.gen'
import {
  dimensionLabel,
  dimensionNameMap,
  flattenTagTree,
  groupTagTreesByDimension,
} from '@/utils/tagTree'
import TagCheckboxTree from '@/components/tag/TagCheckboxTree.vue'
import BaseModal from '@/components/ui/BaseModal.vue'

/**
 * 通用打标弹窗（资源 / 任务 / 用量）
 *
 * 标签树/维度自取（colada 缓存共享）；标签树按维度分组展示（跨维度可重名）；
 * 后端互斥校验失败（409）时内联展示冲突详情，并抑制全局 toast。
 *
 * 支持两种模式：
 * - 单实体：传 `entity`，当前标签通过 useEntityTags 查询
 * - 批量：传 `entities`（多个实体应用同一组标签，逐条调用 setTags 保存），
 *   当前标签由页面传入的 `initialTags`（各实体标签并集）提供
 */
const props = defineProps<{
  show: boolean
  entity: TagEntityRef | null
  /** 弹窗标题与实体描述（如资源名 / 任务名 / 用量描述） */
  entityName: string
  /** 批量模式：需要统一打标的多个实体 */
  entities?: TagEntityRef[] | null
  /** 批量模式：各实体当前标签的并集（未传则从空集开始） */
  initialTags?: TagResp[] | null
}>()

const emit = defineEmits<{
  (e: 'saved'): void
  (e: 'cancel'): void
}>()

const { tagTree } = useTagApi()
const { dimensions } = useTagDimensionApi()

const entityRef = ref<TagEntityRef | null>(null)
const batchEntities = ref<TagEntityRef[]>([])

watch(
  () => props.show,
  (show) => {
    entityRef.value = show ? props.entity : null
    batchEntities.value = show && props.entities && props.entities.length > 0 ? props.entities : []
    formError.value = ''
  },
)

// 单实体模式：查询该实体当前标签；批量模式：直接使用页面传入的并集
const { tags, isLoading: tagsLoading } = useEntityTags(entityRef)

const currentTags = computed(() => {
  if (batchEntities.value.length > 0) return props.initialTags ?? []
  return tags.value
})

const checkedTagIds = ref<number[]>([])

watch(currentTags, (list) => {
  checkedTagIds.value = list.map((t) => t.id)
})

const nameMap = computed(() => dimensionNameMap(dimensions.value))
const groupedTrees = computed(() => groupTagTreesByDimension(tagTree.value))

const tagNameMap = computed(() => {
  const map = new Map<number, string>()
  for (const row of flattenTagTree(tagTree.value)) map.set(row.node.id, row.node.name)
  return map
})

const searchQuery = ref('')
const formError = ref('')

const { setTags, isSetting } = useEntityTagApi()

async function handleSubmit() {
  if (!entityRef.value && batchEntities.value.length === 0) return
  formError.value = ''
  try {
    if (batchEntities.value.length > 0) {
      // 批量模式：同一组标签逐条应用；遇冲突（409）中断并内联展示详情
      for (const e of batchEntities.value) {
        await setTags(e, checkedTagIds.value)
      }
    } else if (entityRef.value) {
      await setTags(entityRef.value, checkedTagIds.value)
    }
    emit('saved')
  } catch (e) {
    formError.value = formatHttpError(e, '保存失败，请重试')
    console.error('Set entity tags failed:', e)
  }
}
</script>

<template>
  <BaseModal :open="show" class="max-w-lg" @close="emit('cancel')">
    <h3 class="font-bold text-lg text-base-content mb-1">为{{ entityName }}打标</h3>
    <p class="text-[11px] text-fg-subtle mb-4">
      标签用于碳排放分类统计；选择器按维度分组，跨维度允许重名
    </p>

    <!-- 已选标签 -->
    <div class="flex items-center gap-2 mb-2">
      <span class="text-xs font-medium text-base-content">已选标签</span>
      <span class="ml-auto text-[11px] text-fg-subtle"
        >可多选，一个{{ entityName }}可归属多个标签</span
      >
    </div>
    <div v-if="checkedTagIds.length > 0" class="flex flex-wrap gap-2 mb-4">
      <span
        v-for="(tagId, index) in checkedTagIds"
        :key="tagId"
        class="inline-flex items-center gap-1.5 h-7 pl-2.5 pr-1.5 rounded-full bg-primary/10 border border-primary/30 text-xs"
      >
        <span class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: getSliceColor(index) }" />
        {{ tagNameMap.get(tagId) ?? `#${tagId}` }}
        <button
          type="button"
          class="btn btn-ghost btn-xs btn-square h-5 min-h-5 w-5"
          :disabled="isSetting"
          aria-label="移除标签"
          @click="checkedTagIds = checkedTagIds.filter((id) => id !== tagId)"
        >
          <span class="material-symbols-outlined text-xs">close</span>
        </button>
      </span>
    </div>
    <p v-else class="text-[11px] text-fg-subtle mb-4">尚未选择标签</p>

    <!-- 互斥冲突错误（后端 409） -->
    <div v-if="formError" class="alert alert-error alert-sm mb-4" role="alert">
      <span class="material-symbols-outlined icon-sm shrink-0">error</span>
      <div class="min-w-0">
        <p class="font-medium">保存失败：标签互斥</p>
        <p class="text-xs mt-0.5 break-words">{{ formError }}</p>
        <p class="text-xs mt-0.5 text-fg-muted">
          该实体在某个图表中已归入其他切片，请移除冲突标签后重试。
        </p>
      </div>
    </div>

    <!-- 标签树（按维度分组） -->
    <div
      class="rounded-field bg-base-200/40 border border-base-content/20 p-3 max-h-[380px] overflow-y-auto"
    >
      <label class="input flex items-center gap-2 mb-2">
        <span class="material-symbols-outlined icon-sm text-fg-subtle">search</span>
        <input
          v-model="searchQuery"
          type="text"
          class="w-full bg-transparent"
          placeholder="搜索标签…"
        />
      </label>
      <div v-if="tagsLoading" class="flex justify-center py-8">
        <span class="loading loading-spinner loading-md text-primary" />
      </div>
      <template v-else-if="groupedTrees.length > 0">
        <div v-for="group in groupedTrees" :key="group.dimensionId" class="mb-3 last:mb-0">
          <p
            class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-base-300/60 text-fg-muted inline-block mb-1"
          >
            {{ dimensionLabel(nameMap, group.dimensionId) }}
          </p>
          <TagCheckboxTree :tree="group.tree" v-model="checkedTagIds" :search="searchQuery" />
        </div>
      </template>
      <p v-else class="text-center py-6 text-xs text-fg-subtle">
        暂无标签，请先在「碳排放标签」中创建
      </p>
    </div>

    <div class="modal-action">
      <button class="btn btn-ghost" type="button" :disabled="isSetting" @click="emit('cancel')">
        取消
      </button>
      <button
        class="btn btn-primary"
        type="button"
        :disabled="isSetting || tagsLoading"
        @click="handleSubmit"
      >
        <span v-if="isSetting" class="loading loading-spinner loading-xs"></span>
        保存
      </button>
    </div>
  </BaseModal>
</template>
