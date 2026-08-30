<script setup lang="ts">
import { computed, ref } from 'vue'
import { useConstraintApi } from '@/composables/useConstraintApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useToast } from '@/composables/useToast'
import { formatHttpError } from '@/utils/error'
import ResourceConstraintForm from '@/components/optimization/ResourceConstraintForm.vue'
import ResourceConstraintList from '@/components/optimization/ResourceConstraintList.vue'
import type { ResourceConstraintResp } from '@/types/constraint'

definePage({
  meta: {
    title: '资源限制',
    description: '限制某项资源的峰值使用量，用于过滤帕累托前沿',
    icon: 'rule',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 4,
  },
})

const { constraints, isLoading, deleteConstraint } = useConstraintApi()
const { currentProjectId } = useProjectContext()
const { notifyError } = useToast()

const showForm = ref(false)
const editingItem = ref<ResourceConstraintResp | null>(null)
const formMode = computed<'create' | 'edit'>(() => (editingItem.value ? 'edit' : 'create'))

function openCreate() {
  editingItem.value = null
  showForm.value = true
}

function handleEdit(constraint: ResourceConstraintResp) {
  editingItem.value = constraint
  showForm.value = true
}

function handleFormSaved() {
  showForm.value = false
  editingItem.value = null
}

function handleFormCancel() {
  showForm.value = false
  editingItem.value = null
}

async function handleDelete(constraint: ResourceConstraintResp) {
  try {
    await deleteConstraint({ path: { project_id: currentProjectId.value!, id: constraint.id } })
    if (editingItem.value?.id === constraint.id) {
      editingItem.value = null
      showForm.value = false
    }
  } catch (e) {
    notifyError({ title: '删除失败', description: formatHttpError(e, '请稍后重试') })
    console.error('Failed to delete constraint:', e)
  }
}
</script>

<template>
  <Teleport defer to="#header-actions">
    <button
      v-if="!showForm"
      type="button"
      class="btn btn-primary px-4 gap-1"
      aria-label="新建资源限制"
      @click="openCreate"
    >
      <span class="material-symbols-outlined icon-sm" aria-hidden="true">add</span>
      资源限制
    </button>
  </Teleport>

  <div class="space-y-4">
    <!-- 表单面板 -->
    <section v-if="showForm" class="p-4 panel" aria-labelledby="constraint-form-title">
      <h2 id="constraint-form-title" class="section-title">
        {{ formMode === 'edit' ? '编辑资源限制' : '新建资源限制' }}
      </h2>
      <ResourceConstraintForm
        :mode="formMode"
        :initial-values="editingItem"
        @saved="handleFormSaved"
        @cancel="handleFormCancel"
      />
    </section>

    <!-- 列表面板 -->
    <section class="panel p-0 overflow-hidden" aria-labelledby="constraint-list-title">
      <div class="px-4 py-2.5 border-b border-base-content/10">
        <h2 id="constraint-list-title" class="section-title !mb-0">限制列表</h2>
      </div>

      <div v-if="isLoading" class="flex justify-center py-10">
        <span class="loading loading-spinner loading-md text-primary" />
      </div>

      <ResourceConstraintList
        v-else
        :constraints="constraints"
        @edit="handleEdit"
        @delete="handleDelete"
      />
    </section>
  </div>
</template>
