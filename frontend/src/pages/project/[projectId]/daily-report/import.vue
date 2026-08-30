<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDailyReportStoreV2 } from '@/stores/report'
import { useMutation } from '@pinia/colada'
import { parseDailyReportMutation } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'
import { todayIsoLocal } from '@/utils/date'

definePage({
  meta: {
    title: '导入日报',
    icon: 'upload_file',
    showInNav: true,
    parentName: '/project/[projectId]/daily-report',
    navOrder: 1,
  },
})

const router = useRouter()
const storeV2 = useDailyReportStoreV2()
const { currentProjectId } = useProjectContext()

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const usageDate = ref(todayIsoLocal())

const { mutateAsync: parseDailyReport, data, isLoading } = useMutation(parseDailyReportMutation())

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    selectedFile.value = file
  }
}

async function handleParse() {
  if (!selectedFile.value || !usageDate.value) return

  storeV2.error = ''

  await parseDailyReport({
    path: { project_id: currentProjectId.value! },
    body: {
      file: selectedFile.value,
      usage_date: usageDate.value,
    },
  })
    .then((result) => {
      storeV2.parsedResourceItems = result.parsedItems
      storeV2.batchId = result.batchId
    })
    .catch((error) => {
      storeV2.error = error
    })
}

function resetImport() {
  storeV2.reset()
  selectedFile.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

function goToReview() {
  router.push('./review')
}
</script>

<template>
  <div class="p-6 pb-24 max-w-3xl mx-auto">
    <div v-if="storeV2.parsedResourceItems.length === 0" class="space-y-4">
      <div class="text-center mb-8">
        <h2 class="text-xl font-semibold text-base-content mb-2">导入日报文件</h2>
        <p class="text-sm text-fg-subtle">
          请上传施工现场的 Excel 日报文件，系统将自动解析资源使用数据
        </p>
      </div>

      <fieldset class="fieldset">
        <legend class="fieldset-legend">使用日期</legend>
        <input v-model="usageDate" type="date" class="input w-full" :disabled="isLoading" />
      </fieldset>

      <label
        class="border-2 border-dashed border-base-300 rounded-lg p-6 text-center cursor-pointer hover:border-primary/50 hover:bg-base-200/50 transition-colors block"
      >
        <span class="flex flex-col items-center gap-3">
          <span class="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-2">
            <span class="material-symbols-outlined icon-2xl text-primary">
              {{ selectedFile ? 'check_circle' : 'upload_file' }}
            </span>
          </span>
          <span class="text-lg font-medium">
            {{ selectedFile ? selectedFile.name : '点击选择文件' }}
          </span>
          <span v-if="selectedFile">
            {{ Math.round(selectedFile.size / 1024).toLocaleString() }} kB
          </span>
          <span v-if="!selectedFile" class="text-xs text-fg-subtle">支持 .xlsx, .xls 格式</span>
        </span>
        <button
          v-if="selectedFile"
          type="button"
          class="btn btn-error translate-y-4"
          @click.self="selectedFile = null"
        >
          点击重选
        </button>
        <input
          v-else
          type="file"
          class="hidden"
          placeholder=""
          accept=".application/vnd.ms-excel"
          @change="handleFileChange"
        />
      </label>

      <div v-if="storeV2.error" class="alert alert-error alert-sm" role="alert">
        <span class="material-symbols-outlined icon-sm">error</span>
        <span>{{ storeV2.error }}</span>
      </div>

      <button
        class="btn btn-primary btn-block"
        :disabled="!selectedFile || !usageDate || isLoading"
        @click="handleParse"
      >
        <span v-if="isLoading" class="loading loading-spinner loading-xs"></span>
        <span v-else class="material-symbols-outlined icon-sm">play_arrow</span>
        <span>{{ isLoading ? '正在解析...' : '开始解析' }}</span>
      </button>

      <div class="panel p-4">
        <h3 class="font-medium text-base-content mb-2 flex items-center gap-2">
          <span class="material-symbols-outlined text-primary icon-sm">info</span>
          导入说明
        </h3>
        <ul class="text-sm text-base-content/70 space-y-1">
          <li>• 确保文件格式为标准的 Excel 表格</li>
          <li>• 文件应包含资源名称、类别、数量等信息</li>
          <li>• 导入后可在下一步核对和编辑数据</li>
        </ul>
      </div>
    </div>

    <div v-else class="space-y-4">
      <div class="card card-border bg-success/10 border-success/30 p-6">
        <div class="flex items-center gap-3 mb-4">
          <div class="w-12 h-12 rounded-full bg-success/20 flex items-center justify-center">
            <span class="material-symbols-outlined icon-xl text-success">check_circle</span>
          </div>
          <div>
            <h3 class="font-semibold text-base-content">导入成功</h3>
            <p class="text-sm text-fg-subtle">
              已解析 {{ storeV2.parsedResourceItems.length }} 项资源数据
            </p>
          </div>
        </div>

        <div v-if="(data?.warnings.length || 0) > 0" class="alert alert-warning alert-sm mb-4">
          <span class="material-symbols-outlined icon-sm">warning</span>
          <div>
            <p class="font-medium">解析警告</p>
            <ul class="text-xs mt-1">
              <li v-for="(warning, index) in data?.warnings" :key="index">
                {{ warning }}
              </li>
            </ul>
          </div>
        </div>

        <div class="flex gap-2">
          <button class="btn btn-outline btn-sm flex-1" @click="resetImport">
            <span class="material-symbols-outlined icon-sm">refresh</span>
            <span>重新导入</span>
          </button>
          <button class="btn btn-primary btn-sm flex-1" @click="goToReview">
            <span>下一步：核对资源</span>
            <span class="material-symbols-outlined icon-sm">arrow_forward</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
