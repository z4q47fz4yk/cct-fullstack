<script setup lang="ts">
import { computed, ref } from 'vue'
import { useReuseConfigApi } from '@/composables/useReuseConfigApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useToast } from '@/composables/useToast'
import ResourceReuseConfigForm from '@/components/optimization/ResourceReuseConfigForm.vue'
import ResourceReuseConfigList from '@/components/optimization/ResourceReuseConfigList.vue'
import type { ResourceReuseConfigResp } from '@/types/reuseConfig'

definePage({
  meta: {
    title: '材料复用',
    description: '设置可周转材料及其周转次数，更精确地计算碳排放',
    icon: 'autorenew',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 6,
  },
})

const { configs, isLoading, deleteConfig } = useReuseConfigApi()
const { currentProjectId } = useProjectContext()
const { notifyError } = useToast()

const showForm = ref(false)
const editingItem = ref<ResourceReuseConfigResp | null>(null)
const formMode = computed<'create' | 'edit'>(() => (editingItem.value ? 'edit' : 'create'))

function openCreate() {
  editingItem.value = null
  showForm.value = true
}

function handleEdit(config: ResourceReuseConfigResp) {
  editingItem.value = config
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

async function handleDelete(config: ResourceReuseConfigResp) {
  // 有全局错误处理，无需再处理
  await deleteConfig({ path: { project_id: currentProjectId.value!, id: config.id } })
  if (editingItem.value?.id === config.id) {
    editingItem.value = null
    showForm.value = false
  }
}
</script>

<template>
  <Teleport defer to="#header-actions">
    <button
      v-if="!showForm"
      type="button"
      class="btn btn-primary px-4 gap-1"
      aria-label="新建可复用材料配置"
      @click="openCreate"
    >
      <span class="material-symbols-outlined icon-sm" aria-hidden="true">add</span>
      可复用材料
    </button>
  </Teleport>

  <div class="space-y-4">
    <!-- 列表面板 -->
    <section class="panel p-0 overflow-hidden" aria-labelledby="reuse-list-title">
      <div class="px-4 py-2.5 border-b border-base-content/10">
        <h2 id="reuse-list-title" class="section-title !mb-0">配置列表</h2>
      </div>

      <div v-if="isLoading" class="flex justify-center py-10">
        <span class="loading loading-spinner loading-md text-primary" />
      </div>

      <ResourceReuseConfigList
        v-else
        :configs="configs"
        @edit="handleEdit"
        @delete="handleDelete"
      />
    </section>

    <!-- 表单面板 -->
    <section v-if="showForm" class="p-4 panel" aria-labelledby="reuse-form-title">
      <h2 id="reuse-form-title" class="section-title">
        {{ formMode === 'edit' ? '编辑复用配置' : '新建复用配置' }}
      </h2>
      <ResourceReuseConfigForm
        :mode="formMode"
        :initial-values="editingItem"
        @saved="handleFormSaved"
        @cancel="handleFormCancel"
      />
    </section>
  </div>
</template>
