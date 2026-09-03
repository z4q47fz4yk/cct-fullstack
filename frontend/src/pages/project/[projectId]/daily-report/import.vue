<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDailyReportStoreV2 } from '@/stores/report'
import { useMutation, useQuery } from '@pinia/colada'
import { listConfigsQuery, parseDailyReportMutation } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'
import { useUsageDateType } from '@/composables/useUsageDateType'

definePage({
  meta: {
    title: '导入日报',
    icon: 'upload_file',
    // 从侧边栏隐藏：统一从「资源使用量」页进入
    showInNav: false,
    parentName: '/project/[projectId]/daily-report',
    navOrder: 1,
  },
})

const route = useRoute()
const router = useRouter()
const storeV2 = useDailyReportStoreV2()
const { currentProjectId } = useProjectContext()

// 使用日期与「资源使用量」页共享（页面级唯一日期）
const { usageDate, effectiveUsageType } = useUsageDateType()

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)

// ─── AI 生成解析配置入口 ─────────────────────────────────────
function gotoAiConfig() {
  const id = currentProjectId.value
  if (id == null) return
  // AI 页用于生成「新」配置；保存成功后回跳 import 并携带新 config_id 自动选中
  router.push(`/project/${id}/daily-report/ai`)
}

// ─── 项目自定义解析配置（AI 生成）选择 ───────────────────────
const { data: configs, isLoading: configsLoading } = useQuery(() => ({
  ...listConfigsQuery({
    path: { project_id: currentProjectId.value! },
  }),
  enabled: currentProjectId.value !== null,
}))

// 选中配置：优先 URL query（AI 页保存后回跳携带），其次手动选择
const selectedConfigId = ref<string | null>(null)

watch(
  () => route.query.config_id as string | undefined,
  (configId) => {
    if (configId && configId !== selectedConfigId.value) {
      selectedConfigId.value = configId
    }
  },
  { immediate: true },
)

// 兜底：URL 携带的 config_id 在本项目配置列表中不存在时清除（防无效选中）
watch(
  () => configs.value,
  (configList) => {
    const cfgId = selectedConfigId.value
    if (cfgId && configList && !configList.some((c) => c.configId === cfgId)) {
      selectedConfigId.value = null
      router.replace({ query: { config_id: undefined } })
    }
  },
)

const selectedConfigName = computed(
  () => configs.value?.find((c) => c.configId === selectedConfigId.value)?.name ?? null,
)

function clearSelectedConfig() {
  selectedConfigId.value = null
  router.replace({ query: { config_id: undefined } })
}

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
      config_id: selectedConfigId.value,
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

      <!-- AI 生成解析配置入口：日报结构特殊/首次导入时，可先用 AI 生成解析配置 -->
      <div class="panel panel-hover p-4 flex flex-wrap items-center gap-3">
        <div class="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined text-primary icon-lg">auto_awesome</span>
        </div>
        <div class="flex-1 min-w-48">
          <p class="font-medium text-base-content">解析不理想？试试 AI 生成解析配置</p>
          <p class="text-xs text-fg-subtle mt-0.5">
            上传日报给 AI 对话，AI 会分析表格结构并生成、校验、保存解析配置
          </p>
        </div>
        <button class="btn btn-primary btn-sm" :disabled="isLoading" @click="gotoAiConfig">
          <span class="material-symbols-outlined icon-sm">auto_awesome</span>
          <span>AI 生成配置</span>
        </button>
      </div>

      <!-- 计划口径提示：日报导入按实际口径落库 -->
      <div
        v-if="effectiveUsageType === 'PLANNED'"
        class="alert alert-warning alert-sm mb-4"
        role="alert"
      >
        <span class="material-symbols-outlined icon-sm">warning</span>
        <span class="text-sm">
          当前为「计划」口径，日报导入将按「实际」口径落库；如需录入计划数据请回到资源使用量页切换口径。
        </span>
      </div>

      <fieldset class="fieldset">
        <legend class="fieldset-legend">使用日期</legend>
        <input v-model="usageDate" type="date" class="input w-full" :disabled="isLoading" />
      </fieldset>

      <!-- 解析配置选择：默认使用内置配置；有 AI 生成的配置时可选用 -->
      <fieldset v-if="configs && configs.length > 0" class="fieldset">
        <legend class="fieldset-legend flex items-center gap-1">
          解析配置
          <span class="text-xs text-fg-subtle font-normal">（留空 = 内置默认配置）</span>
        </legend>
        <div class="flex items-center gap-2">
          <select
            v-model="selectedConfigId"
            class="select w-full"
            :disabled="isLoading || configsLoading"
          >
            <option :value="null">内置默认配置</option>
            <option v-for="cfg in configs" :key="cfg.configId" :value="cfg.configId">
              {{ cfg.name ?? `配置 ${cfg.configId.slice(0, 8)}` }}（{{ cfg.blockCount }} 块 ·
              {{ cfg.categories.join(' / ') }}）
            </option>
          </select>
          <button
            v-if="selectedConfigId"
            class="btn btn-ghost btn-sm"
            title="清除所选配置"
            @click="clearSelectedConfig"
          >
            <span class="material-symbols-outlined icon-sm">close</span>
          </button>
        </div>
        <p v-if="selectedConfigId" class="text-xs text-primary mt-1">
          {{
            selectedConfigName ? `将使用「${selectedConfigName}」解析` : '将使用所选 AI 配置解析'
          }}
        </p>
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
