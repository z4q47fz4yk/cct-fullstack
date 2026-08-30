<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '@pinia/colada'
import { useDailyReportStoreV2 } from '@/stores/report'
import { useProgressApi } from '@/composables/useProgressApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { listTasksQuery } from '@/client/@pinia/colada.gen'
import type { TaskProgressBatchItem } from '@/client/types.gen'
import { notifyError } from '@/composables/useToast'
import { todayIsoLocal } from '@/utils/date'
import AllocationByTask from '@/components/daily-report/AllocationByTask.vue'
import AllocationByResource from '@/components/daily-report/AllocationByResource.vue'

definePage({
  meta: {
    title: '确认提交',
    icon: 'check_circle',
    showInNav: true,
    parentName: '/project/[projectId]/daily-report',
    navOrder: 4,
  },
})

const store = useDailyReportStoreV2()
const router = useRouter()
const { currentProjectId } = useProjectContext()
const { recordProgressBatch, isRecording } = useProgressApi()

// ──── 当日工序进度（可选，随日报提交） ─────────────────────
const tasksQuery = useQuery(() => ({
  ...listTasksQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: FETCH_ALL_PAGE_SIZE },
  }),
  enabled: !!currentProjectId.value,
}))
const taskById = computed(
  () => new Map((tasksQuery.state.value?.data?.items ?? []).map((t) => [t.id, t])),
)

// 本地时区“今天”（toISOString 为 UTC，跨时区会取到昨天）
const todayIso = todayIsoLocal

const involvedTaskIds = computed(() => Array.from(store.allocatedResourceQuantities.keys()))
const progressEntries = ref<Record<number, number>>({})

function progressValue(taskId: number): string {
  const v = progressEntries.value[taskId]
  return v === undefined || v === null ? '' : String(v)
}

function setProgressValue(taskId: number, raw: string) {
  const n = Number(raw)
  progressEntries.value[taskId] = Number.isNaN(n) ? 0 : Math.min(Math.max(n, 0), 100)
}

async function handleSubmit() {
  try {
    await store.submitReport()
  } catch (e) {
    console.error('Submit report failed:', e)
    return
  }

  const items: TaskProgressBatchItem[] = []
  for (const tid of involvedTaskIds.value) {
    const percent = progressEntries.value[tid] ?? 0
    if (percent > 0) items.push({ task_id: tid, date: todayIso(), percent })
  }
  if (items.length > 0) {
    try {
      await recordProgressBatch(items)
    } catch (e) {
      console.error('Submit progress failed:', e)
      notifyError({ title: '资源已提交，但进度录入失败', description: '可稍后在任务管理中补录' })
    }
  }
  router.push('./success')
}

// 数据未就绪引导:仅用于主体显示说明,不进行自动跳转
type BlockInfo = { title: string; description: string; target: string; label: string } | null
const blockInfo = computed<BlockInfo>(() => {
  if (!store.batchId || store.parsedResourceItems.length === 0) {
    return {
      title: '尚未导入日报',
      description: '提交前需要先在导入日报页面上传文件并解析。',
      target: './import',
      label: '导入日报',
    }
  }
  if (store.currentPhase === 'PENDING') {
    return {
      title: '请先完成资源核对',
      description: '需要先在资源核对页面确认资源映射关系。',
      target: './review',
      label: '资源核对',
    }
  }
  if (store.currentPhase === 'MAPPING' && store.resourceUsages.length === 0) {
    return {
      title: '请先完成工序分配',
      description: '提交前需要为每个工序分配资源使用量。',
      target: './allocate',
      label: '分配工序',
    }
  }
  return null
})

const isReadyToSubmit = computed(() => blockInfo.value === null)
const blockTitle = computed(() => blockInfo.value?.title ?? '')
const blockDescription = computed(() => blockInfo.value?.description ?? '')
const guideTarget = computed(() => blockInfo.value?.target ?? '')
const guideLabel = computed(() => blockInfo.value?.label ?? '')

type SummaryView = 'task' | 'resource'
const activeView = ref<SummaryView>('task')

function goToGuide() {
  if (guideTarget.value) router.push(guideTarget.value)
}
</script>

<template>
  <div class="p-6 pb-24 max-w-4xl mx-auto">
    <!-- 数据未就绪:大空白态 -->
    <div v-if="!isReadyToSubmit" class="text-center py-8">
      <div
        class="w-20 h-20 rounded-full bg-base-200 flex items-center justify-center mx-auto mb-4 border border-base-300"
      >
        <span class="material-symbols-outlined icon-2xl text-base-content/30">pending_actions</span>
      </div>
      <h3 class="text-lg font-semibold text-base-content/70 mb-2">{{ blockTitle }}</h3>
      <p class="text-fg-subtle mb-4">{{ blockDescription }}</p>
      <button class="btn btn-primary" @click="goToGuide">
        <span class="material-symbols-outlined">arrow_forward</span>
        <span>前往 {{ guideLabel }}</span>
      </button>
    </div>

    <!-- 数据已就绪:正常内容 -->
    <div v-else class="space-y-4">
      <div class="grid grid-cols-2 gap-4 mb-4">
        <div class="panel panel-hover p-4">
          <div class="flex items-center gap-2 mb-2">
            <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <span class="material-symbols-outlined text-primary icon-sm">inventory_2</span>
            </div>
            <span class="text-sm text-fg-subtle">资源总数</span>
          </div>
          <div class="text-2xl font-semibold font-num text-base-content">
            {{ store.summaryStats.totalResources }}
          </div>
        </div>

        <div class="panel panel-hover p-4">
          <div class="flex items-center gap-2 mb-2">
            <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <span class="material-symbols-outlined text-primary icon-sm">construction</span>
            </div>
            <span class="text-sm text-fg-subtle">分配工序</span>
          </div>
          <div class="text-2xl font-semibold font-num text-base-content">
            {{ store.summaryStats.allocatedTasks }}
          </div>
          <div class="text-xs text-fg-subtle">{{ store.summaryStats.totalAllocations }} 项分配</div>
        </div>
      </div>

      <div class="join grid grid-cols-2">
        <button
          type="button"
          class="join-item btn"
          :class="activeView === 'task' ? 'btn-primary' : 'btn-outline'"
          @click="activeView = 'task'"
        >
          <span class="material-symbols-outlined icon-sm">construction</span>
          <span>按工序汇总</span>
        </button>
        <button
          type="button"
          class="join-item btn"
          :class="activeView === 'resource' ? 'btn-primary' : 'btn-outline'"
          @click="activeView = 'resource'"
        >
          <span class="material-symbols-outlined icon-sm">inventory_2</span>
          <span>按资源汇总</span>
        </button>
      </div>

      <AllocationByTask v-if="activeView === 'task'" disable-action />
      <AllocationByResource v-else />

      <!-- 当日工序进度（可选） -->
      <div class="panel p-4">
        <div class="flex items-center justify-between mb-1">
          <h3 class="text-sm font-semibold text-base-content">当日工序进度（可选）</h3>
          <span class="text-xs text-fg-subtle font-mono">{{ todayIso() }}</span>
        </div>
        <p class="text-xs text-fg-subtle mb-3">
          为涉及工序录入当日完成百分比（0-100），进度到 100% 即判定该工序完成；留空则不更新
        </p>
        <div v-if="involvedTaskIds.length === 0" class="text-sm text-fg-muted py-2">
          暂无分配工序
        </div>
        <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-2">
          <div
            v-for="tid in involvedTaskIds"
            :key="tid"
            class="flex items-center gap-3 rounded-lg border border-base-content/10 px-3 py-2"
          >
            <div class="flex-1 min-w-0">
              <p class="text-sm text-base-content truncate">
                {{ taskById.get(tid)?.code }} {{ taskById.get(tid)?.name ?? `工序 #${tid}` }}
              </p>
            </div>
            <label class="input input-xs input-bordered w-28 flex items-center gap-1">
              <input
                type="number"
                min="0"
                max="100"
                step="5"
                class="w-full bg-transparent outline-none font-num"
                :value="progressValue(tid)"
                placeholder="0-100"
                @input="setProgressValue(tid, ($event.target as HTMLInputElement).value)"
              />
              <span class="text-xs text-fg-subtle">%</span>
            </label>
          </div>
        </div>
      </div>

      <div v-if="store.error" class="alert alert-error alert-sm mb-4" role="alert">
        <span class="material-symbols-outlined icon-sm">error</span>
        <span>{{ store.error }}</span>
      </div>

      <div class="pt-4">
        <button
          class="btn btn-primary btn-block"
          :disabled="store.isLoading || isRecording"
          @click="handleSubmit"
        >
          <span
            v-if="store.isLoading || isRecording"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="material-symbols-outlined">rocket_launch</span>
          <span>{{ store.isLoading || isRecording ? '提交中...' : '提交到引擎' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
