<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import BasicLayout from '@/components/layout/BasicLayout.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import SegmentControl from '@/components/common/SegmentControl.vue'
import { useProjectApi } from '@/composables/useProjectApi'
import type { ProjectResp } from '@/client/types.gen'

definePage({
  meta: { title: '项目列表', description: '选择或创建一个施工项目开始优化' },
})

const router = useRouter()
const api = useProjectApi()
const { projects, isLoading, error, createProject, isCreating } = api

// 创建项目对话框
const showCreateDialog = ref(false)
const newProjectName = ref('')
const newProjectDescription = ref('')

// 视图切换：卡片 / 列表（设计稿 tabbar）
const viewMode = ref<'card' | 'list'>('card')

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

function fmtArea(v?: number | null) {
  return v ? `${v.toLocaleString('zh-CN')}㎡` : null
}

function fmtDate(s: string) {
  return s.slice(0, 10)
}

/** 项目状态 → 标签（设计稿 tag：计划中/施工中/已完成） */
const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  PLANNING: { label: '计划中', cls: 'badge-info' },
  CONSTRUCTION: { label: '施工中', cls: 'badge-success' },
  COMPLETED: { label: '已完成', cls: 'badge-neutral' },
}
function statusBadge(status?: string) {
  return STATUS_BADGE[status ?? ''] ?? { label: '计划中', cls: 'badge-info' }
}
</script>

<template>
  <BasicLayout>
    <div class="max-w-6xl mx-auto py-4">
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

      <template v-else>
        <!-- 页头：标题 + 视图切换 + 创建 -->
        <div class="flex items-end justify-between mb-4 gap-4 flex-wrap">
          <div>
            <h2 class="text-xl font-bold text-base-content">项目列表</h2>
            <p class="text-sm text-fg-muted mt-0.5">选择或创建一个施工项目开始优化</p>
          </div>
          <div class="flex items-center gap-2.5">
            <SegmentControl
              v-model="viewMode"
              :options="[
                { value: 'card', label: '卡片', icon: 'grid_view' },
                { value: 'list', label: '列表', icon: 'view_list' },
              ]"
              aria-label="项目视图"
            />
            <button class="btn btn-primary gap-1.5" @click="openCreateDialog">
              <span class="material-symbols-outlined icon-sm">add</span>
              创建项目
            </button>
          </div>
        </div>

        <!-- 卡片视图（设计稿：指标行 + 虚线创建卡） -->
        <div v-if="viewMode === 'card'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="project in projects"
            :key="project.id"
            class="panel panel-hover p-4 cursor-pointer"
            @click="enterProject(project)"
          >
            <div class="flex items-start justify-between gap-2">
              <h3 class="font-semibold text-base-content truncate">{{ project.name }}</h3>
              <span class="badge shrink-0" :class="statusBadge(project.status).cls">
                <span class="w-1.5 h-1.5 rounded-full bg-current" />{{ statusBadge(project.status).label }}
              </span>
            </div>
            <p v-if="project.description" class="text-[13px] text-fg-muted line-clamp-2 mt-2 mb-3 min-h-10">
              {{ project.description }}
            </p>
            <p v-else class="text-[13px] text-fg-subtle italic mt-2 mb-3 min-h-10">暂无描述</p>
            <div class="flex items-center gap-4 flex-wrap text-xs text-fg-muted">
              <span v-if="fmtArea(project.building_area)" class="inline-flex items-center gap-1">
                <span class="material-symbols-outlined icon-xs">domain</span>
                {{ fmtArea(project.building_area) }}
              </span>
              <span v-if="fmtArea(project.land_area)" class="inline-flex items-center gap-1">
                <span class="material-symbols-outlined icon-xs">map</span>
                {{ fmtArea(project.land_area) }}
              </span>
              <span class="inline-flex items-center gap-1">
                <span class="material-symbols-outlined icon-xs">schedule</span>
                {{ fmtDate(project.created_at) }}
              </span>
            </div>
          </div>

          <!-- 虚线创建卡 -->
          <div
            class="panel border-dashed flex flex-col items-center justify-center gap-2 text-fg-muted min-h-[136px] cursor-pointer hover:text-primary hover:border-primary/50 transition-colors"
            @click="openCreateDialog"
          >
            <span class="material-symbols-outlined icon-xl text-fg-subtle">add</span>
            <span class="text-sm">创建新项目</span>
          </div>
        </div>

        <!-- 列表视图 -->
        <div v-else class="panel">
          <div class="overflow-x-auto">
            <table class="table">
              <thead>
                <tr>
                  <th>项目名称</th>
                  <th>项目描述</th>
                  <th class="table-num">建筑面积(㎡)</th>
                  <th class="table-num">占地面积(㎡)</th>
                  <th>创建时间</th>
                  <th>状态</th>
                  <th class="w-24">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="project in projects" :key="project.id" class="cursor-pointer" @click="enterProject(project)">
                  <td class="font-medium text-primary">{{ project.name }}</td>
                  <td class="max-w-64 truncate text-fg-muted">{{ project.description || '—' }}</td>
                  <td class="table-num">{{ project.building_area?.toLocaleString('zh-CN') ?? '—' }}</td>
                  <td class="table-num">{{ project.land_area?.toLocaleString('zh-CN') ?? '—' }}</td>
                  <td class="text-fg-muted">{{ fmtDate(project.created_at) }}</td>
                  <td>
                    <span class="badge" :class="statusBadge(project.status).cls">
                      <span class="w-1.5 h-1.5 rounded-full bg-current" />{{ statusBadge(project.status).label }}
                    </span>
                  </td>
                  <td>
                    <button
                      class="btn btn-sm btn-primary"
                      @click.stop="enterProject(project)"
                    >
                      进入
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
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
        <button class="btn btn-outline" :disabled="isCreating" @click="showCreateDialog = false">
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
