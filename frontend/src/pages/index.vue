<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import BasicLayout from '@/components/layout/BasicLayout.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { useProjectApi } from '@/composables/useProjectApi'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { formatHttpError } from '@/utils/error'
import type { ProjectResp } from '@/client/types.gen'

definePage({
  meta: { title: '项目列表', description: '选择或创建一个项目' },
})

/** 项目名称长度上限（与后端 ProjectCreate.name 的 string_too_long 约束一致） */
const PROJECT_NAME_MAX = 100

const router = useRouter()
const api = useProjectApi()
const {
  projects,
  isLoading,
  error,
  createProject,
  isCreating,
  deleteProjectById,
  isDeletingProject,
} = api
const { confirmDanger } = useConfirm()
const { notifyError, notifySuccess } = useToast()

// 创建项目对话框
const showCreateDialog = ref(false)
const newProjectName = ref('')
const newProjectDescription = ref('')
// 创建失败的错误文案（保留弹窗并内联展示后端返回的可读 message）
const createError = ref('')

// 前端长度预检：超长直接拦截，避免提交后才收到 422
const nameTooLong = computed(() => newProjectName.value.length > PROJECT_NAME_MAX)

function enterProject(project: ProjectResp) {
  router.push(`/project/${project.id}/schedule`)
}

function openCreateDialog() {
  showCreateDialog.value = true
  newProjectName.value = ''
  newProjectDescription.value = ''
  createError.value = ''
}

async function handleCreate() {
  const name = newProjectName.value.trim()
  if (!name || nameTooLong.value) return
  createError.value = ''
  try {
    const result = await createProject({
      name,
      description: newProjectDescription.value.trim() || null,
    })
    showCreateDialog.value = false
    // 创建后直接进入新项目
    if (result?.id) {
      router.push(`/project/${result.id}/schedule`)
    }
  } catch (e) {
    // 422（如名称超长）/409 等失败：弹窗保持打开，内联 + toast 展示后端错误文案
    createError.value = formatHttpError(e, '创建项目失败，请重试')
    notifyError({ title: '创建项目失败', description: createError.value })
    console.error('Failed to create project:', e)
  }
}

// 删除项目（破坏性操作：二次确认 → 失败 toast + 控制台日志；成功后列表缓存自动失效刷新）
async function handleDeleteProject(project: ProjectResp) {
  const ok = await confirmDanger(
    `确定要删除项目「${project.name}」吗？该项目下的工序、资源、用量、优化记录等全部数据将被一并删除，且不可恢复。`,
    '删除项目',
  )
  if (!ok.confirmed) return
  try {
    await deleteProjectById(project.id)
    notifySuccess({ title: '项目已删除', description: `「${project.name}」已删除` })
  } catch (e) {
    notifyError({ title: '删除项目失败', description: formatHttpError(e) })
    console.error('Failed to delete project:', e)
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
                <button
                  type="button"
                  class="btn btn-ghost btn-xs btn-square text-error hover:bg-error/10"
                  title="删除项目"
                  aria-label="删除项目"
                  :disabled="isDeletingProject"
                  @click.stop="handleDeleteProject(project)"
                >
                  <span class="material-symbols-outlined icon-sm">delete</span>
                </button>
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
        <!-- 创建失败：内联展示后端错误文案（弹窗保持打开） -->
        <div v-if="createError" class="alert alert-error" role="alert">
          <span class="material-symbols-outlined" aria-hidden="true">error</span>
          <span>创建失败：{{ createError }}</span>
        </div>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">项目名称 <span class="text-error">*</span></legend>
          <input
            v-model="newProjectName"
            type="text"
            class="input w-full"
            :class="{ 'input-error': nameTooLong }"
            placeholder="例如：某某高速公路项目"
            :disabled="isCreating"
          />
          <div class="mt-1 flex items-center justify-between text-xs">
            <span v-if="nameTooLong" class="text-error">
              项目名称不能超过 {{ PROJECT_NAME_MAX }} 个字符
            </span>
            <span v-else class="text-fg-subtle">最多 {{ PROJECT_NAME_MAX }} 个字符</span>
            <span class="font-num" :class="nameTooLong ? 'text-error' : 'text-fg-subtle'">
              {{ newProjectName.length }} / {{ PROJECT_NAME_MAX }}
            </span>
          </div>
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
          :disabled="!newProjectName.trim() || nameTooLong || isCreating"
          @click="handleCreate"
        >
          <span v-if="isCreating" class="loading loading-spinner loading-xs"></span>
          {{ isCreating ? '创建中...' : '创建' }}
        </button>
      </template>
    </BaseModal>
  </BasicLayout>
</template>
