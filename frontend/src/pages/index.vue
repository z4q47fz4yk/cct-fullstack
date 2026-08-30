<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import BasicLayout from '@/components/layout/BasicLayout.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { useProjectApi } from '@/composables/useProjectApi'
import type { ProjectResp } from '@/client/types.gen'

definePage({
  meta: { title: '项目列表', description: '选择或创建一个项目' },
})

const router = useRouter()
const api = useProjectApi()
const { projects, isLoading, error, createProject, isCreating } = api

// 创建项目对话框
const showCreateDialog = ref(false)
const newProjectName = ref('')
const newProjectDescription = ref('')

function enterProject(project: ProjectResp) {
  router.push(`/project/${project.id}/schedule`)
}

function openCreateDialog() {
  showCreateDialog.value = true
  newProjectName.value = ''
  newProjectDescription.value = ''
}

async function handleCreate() {
  if (!newProjectName.value.trim()) return
  const result = await createProject({
    name: newProjectName.value.trim(),
    description: newProjectDescription.value.trim() || null,
  })
  showCreateDialog.value = false
  // 创建后直接进入新项目
  if (result?.id) {
    router.push(`/project/${result.id}/schedule`)
  }
}
</script>

<template>
  <BasicLayout>
    <div class="max-w-4xl mx-auto py-8">
      <!-- 加载状态 -->
      <div v-if="isLoading" class="flex justify-center py-8">
        <span class="loading loading-spinner loading-lg text-primary"></span>
      </div>

      <!-- 错误状态 -->
      <div v-else-if="error" class="alert alert-error">
        <span class="material-symbols-outlined">error</span>
        <span>加载项目列表失败</span>
        <button class="btn btn-sm" @click="api.refresh()">重试</button>
      </div>

      <!-- 项目列表为空 -->
      <div v-else-if="projects.length === 0" class="text-center py-8">
        <div
          class="w-20 h-20 rounded-full bg-base-200 flex items-center justify-center mx-auto mb-4"
        >
          <span class="material-symbols-outlined icon-2xl text-base-content/30">folder</span>
        </div>
        <h3 class="text-lg font-semibold text-base-content/70">暂无项目</h3>
        <p class="text-sm text-fg-subtle mt-1 mb-4">创建你的第一个项目开始使用</p>
        <button class="btn btn-primary gap-2" @click="openCreateDialog">
          <span class="material-symbols-outlined icon-sm">add</span>
          创建项目
        </button>
      </div>

      <!-- 项目卡片列表 -->
      <div v-else class="space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold text-base-content">共 {{ projects.length }} 个项目</h2>
          <button class="btn btn-primary btn-sm gap-2" @click="openCreateDialog">
            <span class="material-symbols-outlined icon-sm">add</span>
            创建项目
          </button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="project in projects"
            :key="project.id"
            class="panel panel-hover p-4 cursor-pointer hover:border-primary/50"
            @click="enterProject(project)"
          >
            <div>
              <div class="flex items-center gap-3 mb-2">
                <div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                  <span class="material-symbols-outlined text-primary icon-lg">folder</span>
                </div>
                <div class="flex-1 min-w-0">
                  <h3 class="font-semibold text-base-content truncate">{{ project.name }}</h3>
                </div>
              </div>
              <p v-if="project.description" class="text-sm text-neutral-content/80 line-clamp-2">
                {{ project.description }}
              </p>
              <p v-else class="text-sm text-neutral-content/40 italic">暂无描述</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建项目对话框 -->
    <BaseModal
      v-model:open="showCreateDialog"
      title="创建新项目"
      class="max-w-md"
      @close="showCreateDialog = false"
    >
      <div class="space-y-4">
        <fieldset class="fieldset">
          <legend class="fieldset-legend">项目名称 <span class="text-error">*</span></legend>
          <input
            v-model="newProjectName"
            type="text"
            class="input w-full"
            placeholder="例如：某某高速公路项目"
            :disabled="isCreating"
          />
        </fieldset>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">项目描述</legend>
          <textarea
            v-model="newProjectDescription"
            class="textarea w-full"
            placeholder="可选，简要描述项目内容"
            :disabled="isCreating"
            rows="3"
          />
        </fieldset>
      </div>
      <template #actions>
        <button class="btn btn-ghost" :disabled="isCreating" @click="showCreateDialog = false">
          取消
        </button>
        <button
          class="btn btn-primary"
          :disabled="!newProjectName.trim() || isCreating"
          @click="handleCreate"
        >
          <span v-if="isCreating" class="loading loading-spinner loading-xs"></span>
          {{ isCreating ? '创建中...' : '创建' }}
        </button>
      </template>
    </BaseModal>
  </BasicLayout>
</template>
