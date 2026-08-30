<script setup lang="ts">
import { computed, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import { vTagCreate } from '@/client/valibot.gen'
import BaseModal from '@/components/ui/BaseModal.vue'
import type { TagDimensionResp, TagNodeResp } from '@/client/types.gen'
import { flattenTagTree } from '@/utils/tagTree'

/**
 * 新建 / 编辑标签弹窗（S2）
 *
 * - 新建：必选标签维度（后端契约：dimensionId 必填，跨维度允许重名）；可指定父标签（同维度树形下拉）
 * - 编辑：维度固定不可改；父标签下拉仅列同维度标签
 */
const props = defineProps<{
  show: boolean
  /** 当前维度的标签树（父级候选仅限本维度） */
  tree: TagNodeResp[]
  /** null = 新建；否则为编辑对象 */
  editingTag: TagNodeResp | null
  /** 新建时预置的父标签（如点击"添加子标签"） */
  defaultParentId: number | null
  /** 当前维度（添加子标签 / 编辑时的固定维度） */
  dimensionId: number | null
  dimensions: TagDimensionResp[]
  /** 编辑时的描述预填（TagNodeResp 不含描述，由页面从详情接口传入） */
  editingDescription?: string
  isSubmitting?: boolean
  error?: string
}>()

const emit = defineEmits<{
  (
    e: 'submit',
    payload: { name: string; dimensionId: number; parentId: number | null; description: string },
  ): void
  (e: 'cancel'): void
}>()

// 使用后端生成的完整 schema：dimensionId 必填由表单校验统一保证
const { handleSubmit, resetForm, errors, meta, defineField, setFieldValue } = useForm({
  validationSchema: toTypedSchema(vTagCreate),
  initialValues: {
    name: '',
    dimensionId: undefined as number | undefined,
    parentId: null as number | null,
    description: '',
  },
})

const [name, nameAttrs] = defineField('name')
const [dimensionIdField, dimensionIdAttrs] = defineField('dimensionId')
const [parentId, parentIdAttrs] = defineField('parentId')
const [description, descriptionAttrs] = defineField('description')

// 树形下拉选项：展平 + 缩进层级（父级只能来自当前维度）
const parentOptions = computed(() => {
  const options = flattenTagTree(props.tree)
  // 编辑时不允许选自己或自己的子孙（会形成环）
  const blocked = new Set<number>()
  if (props.editingTag) {
    function collect(node: TagNodeResp) {
      blocked.add(node.id)
      node.children?.forEach(collect)
    }
    collect(props.editingTag)
  }
  return options.filter((o) => !blocked.has(o.node.id))
})

function depthPrefix(depth: number): string {
  return '　'.repeat(depth)
}

const isEditing = computed(() => props.editingTag !== null)

const hasDimensions = computed(() => props.dimensions.length > 0)

watch(
  () => props.show,
  (show) => {
    if (!show) return
    const editing = props.editingTag
    resetForm({
      values: {
        name: editing?.name ?? '',
        dimensionId: editing?.dimensionId ?? props.dimensionId ?? undefined,
        parentId: editing ? (editing.parentId ?? null) : props.defaultParentId,
        description: props.editingDescription ?? '',
      },
    })
  },
)

// 新建时选择维度后清空父级（父级必须属于该维度）
watch(dimensionIdField, () => {
  if (isEditing.value) return
  setFieldValue('parentId', null)
})

function onSubmit() {
  emit('submit', {
    name: name.value?.trim() ?? '',
    dimensionId: dimensionIdField.value!,
    parentId: parentId.value ?? null,
    description: description.value?.trim() ?? '',
  })
}
</script>

<template>
  <BaseModal :open="show" class="max-w-md" @close="emit('cancel')">
    <h3 class="font-bold text-lg text-base-content mb-1">
      {{ isEditing ? '编辑标签' : '新建标签' }}
    </h3>
    <p class="text-xs text-fg-subtle mb-4">
      {{ isEditing ? '修改标签信息，父标签为空表示移动到顶级' : '先选维度再创建，跨维度允许重名' }}
    </p>

    <form class="space-y-4" @submit.prevent="handleSubmit(onSubmit)()">
      <div class="fieldset">
        <label class="fieldset-label">标签名称</label>
        <input
          v-model="name"
          v-bind="nameAttrs"
          :disabled="isSubmitting"
          class="input"
          :class="{ 'input-error': errors.name }"
          placeholder="如：地下工程支护"
          type="text"
        />
        <span v-if="errors.name" class="label text-error">{{ errors.name }}</span>
      </div>

      <div class="fieldset">
        <label class="fieldset-label">标签维度</label>
        <select
          v-if="!isEditing"
          v-model="dimensionIdField"
          v-bind="dimensionIdAttrs"
          :disabled="isSubmitting"
          class="select input w-full"
          :class="{ 'select-error': errors.dimensionId }"
        >
          <option :value="undefined" disabled>请选择维度</option>
          <option v-for="d in dimensions" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
        <div v-else class="input flex items-center gap-2 h-[42px] px-3 text-sm text-fg-muted">
          <span class="material-symbols-outlined icon-sm text-primary">account_tree</span>
          {{
            dimensions.find((d) => d.id === dimensionIdField)?.name ?? `维度 #${dimensionIdField}`
          }}
        </div>
        <span v-if="errors.dimensionId" class="label text-error">{{ errors.dimensionId }}</span>
        <span v-else class="text-xs text-fg-subtle">标签必须属于某个维度</span>
      </div>

      <div class="fieldset">
        <label class="fieldset-label">父标签</label>
        <select
          v-model="parentId"
          v-bind="parentIdAttrs"
          :disabled="isSubmitting || !dimensionIdField"
          class="select input w-full"
        >
          <option :value="null">顶级标签（无父级）</option>
          <option v-for="opt in parentOptions" :key="opt.node.id" :value="opt.node.id">
            {{ depthPrefix(opt.depth) }}{{ opt.node.name }}
          </option>
        </select>
        <span class="text-xs text-fg-subtle">父级只能来自当前维度</span>
      </div>

      <div class="fieldset">
        <label class="fieldset-label">描述</label>
        <textarea
          v-model="description"
          v-bind="descriptionAttrs"
          :disabled="isSubmitting"
          class="textarea input w-full"
          placeholder="可选，说明该标签覆盖的资源范围"
          rows="2"
        ></textarea>
        <span v-if="errors.description" class="text-xs text-error mt-1">
          {{ errors.description }}
        </span>
      </div>

      <div v-if="error" class="alert alert-error alert-sm">
        <span class="material-symbols-outlined icon-sm">error</span>
        <span class="text-sm">{{ error }}</span>
      </div>

      <div class="modal-action">
        <button
          class="btn btn-ghost"
          type="button"
          :disabled="isSubmitting"
          @click="emit('cancel')"
        >
          取消
        </button>
        <button
          class="btn btn-primary"
          type="submit"
          :disabled="isSubmitting || !meta.valid || !hasDimensions"
        >
          <span v-if="isSubmitting" class="loading loading-spinner loading-xs"></span>
          <span>{{ isEditing ? '保存' : '创建' }}</span>
        </button>
      </div>
    </form>
  </BaseModal>
</template>
