<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import MarkdownStream from '@/components/common/MarkdownStream.vue'
import { useProjectContext } from '@/composables/useProjectContext'
import { useAiChat, type AiMessage, type AiToolCall } from '@/composables/useAiChat'
import { useAiUsage } from '@/composables/useAiUsage'

definePage({
  meta: {
    title: 'AI 生成解析配置',
    icon: 'auto_awesome',
    // 从侧边栏隐藏：AI 配置生成是「导入日报」向导的前置步骤，
    // 从导入日报页的引导卡片进入
    showInNav: false,
    parentName: '/project/[projectId]/daily-report',
    navOrder: 0,
  },
})

const router = useRouter()
const { currentProjectId } = useProjectContext()

const { messages, isStreaming, send, stop, clear } = useAiChat()
const { data: usageData, refresh: refreshUsage } = useAiUsage()

const input = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFiles = ref<File[]>([])
const scrollAnchor = ref<HTMLElement | null>(null)

const projectReady = computed(() => currentProjectId.value !== null)

const canSend = computed(
  () => input.value.trim().length > 0 && !isStreaming.value && projectReady.value,
)

// 离开页面时若仍在生成 → 通知后端中止（避免 pi 进程残留生成）
onUnmounted(() => {
  if (isStreaming.value) void stop()
})

// 新消息加入时滚动到底部
watch(
  () => messages.value.length,
  async () => {
    await nextTick()
    scrollToBottom()
  },
)

// AI 流式 reveal 由 MarkdownStream 子组件 rAF 驱动；这里 rAF 去重后跟随滚动，
// 避免子组件每帧 reveal 触发大量 scrollIntoView 排队
let scrollRaf: number | null = null
function handleReveal() {
  if (scrollRaf !== null) return
  scrollRaf = requestAnimationFrame(async () => {
    scrollRaf = null
    await nextTick()
    scrollToBottom()
  })
}
function scrollToBottom() {
  scrollAnchor.value?.scrollIntoView({ behavior: 'smooth' })
}

// ─── 配置产出状态（从消息数据派生） ─────────────────────────────

function findSavedConfigId(msg: AiMessage): string | null {
  const call = msg.toolCall
  if (call && call.name === 'save_report_config' && !call.isError && call.result) {
    try {
      const parsed = JSON.parse(call.result) as { configId?: string; config_id?: string }
      return parsed.configId ?? parsed.config_id ?? null
    } catch {
      return null
    }
  }
  return null
}

/** 任一消息中 save_report_config 成功即置真 */
const configSaved = computed(() =>
  messages.value.some((m) => m.toolCall?.name === 'save_report_config' && !m.toolCall?.isError),
)

/** 最新一次保存成功的配置 ID（回导入页时携带以自动选中） */
const savedConfigId = computed(() => {
  if (!configSaved.value) return null
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const msg = messages.value[i]
    if (!msg) continue
    const id = findSavedConfigId(msg)
    if (id !== null) return id
  }
  return null
})

// ─── 工具过程展示辅助 ──────────────────────────────────────────

const TOOL_LABELS: Record<string, string> = {
  get_project_context: '获取项目上下文',
  extract_report_preview: '提取日报预览',
  validate_report_config: '校验解析配置',
  save_report_config: '保存解析配置',
}

function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name
}

function summarizeArgs(args: Record<string, unknown>): string {
  try {
    const keys = Object.keys(args)
    if (keys.length === 0) return ''
    return keys
      .map((k) => {
        const v = args[k]
        const s = typeof v === 'string' ? v : JSON.stringify(v)
        return `${k}=${s.length > 40 ? s.slice(0, 40) + '…' : s}`
      })
      .join('，')
  } catch {
    return ''
  }
}

function toolIsRunning(call: AiToolCall): boolean {
  return call.result === undefined
}

function toolIsError(call: AiToolCall): boolean {
  return call.isError === true
}

function resultSummary(call: AiToolCall): string {
  const r = call.result
  if (!r) return ''
  if (call.name === 'save_report_config' && !call.isError) {
    try {
      const parsed = JSON.parse(r) as { configId?: string; config_id?: string }
      const id = parsed.configId ?? parsed.config_id
      return id ? `配置已保存（ID: ${id}）` : '配置已保存'
    } catch {
      return '配置已保存'
    }
  }
  if (call.isError) return `失败：${r.slice(0, 80)}`
  // 工具结果很长时截断展示
  return r.length > 120 ? r.slice(0, 120) + '…' : r
}

// ─── 输入与发送 ────────────────────────────────────────────────

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files ?? [])
  selectedFiles.value = [...selectedFiles.value, ...files]
  if (fileInput.value) fileInput.value.value = ''
}

function removeFile(index: number) {
  selectedFiles.value.splice(index, 1)
}

function pickFile() {
  fileInput.value?.click()
}

async function handleSend() {
  const message = input.value.trim()
  if (!message || isStreaming.value || !projectReady.value) return

  input.value = ''
  const files = [...selectedFiles.value]
  selectedFiles.value = []

  try {
    await send({
      message,
      attachments: files,
    })
    // 本轮结束（含中止）后刷新成本审计
    refreshUsage()
  } catch {
    // send 内部已把错误落到消息，无需额外处理
  }
}

function handleStop() {
  void stop()
}

function handleClear() {
  clear()
  selectedFiles.value = []
}

const SUGGESTIONS = ['帮我根据这份日报生成解析配置', '请先查看日报结构，再编写并校验配置']

// ─── 导航 ────────────────────────────────────────────────────

function goBackToImport() {
  const id = currentProjectId.value
  if (id == null) return
  // 已保存新配置时携带 config_id，导入页自动选中并可直接用于解析
  const query = savedConfigId.value ? `?config_id=${encodeURIComponent(savedConfigId.value)}` : ''
  router.push(`/project/${id}/daily-report/import${query}`)
}
</script>

<template>
  <div class="p-6 pb-24 max-w-4xl mx-auto flex flex-col gap-4 h-[calc(100dvh-7rem)]">
    <!-- 头部 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <button
          class="btn btn-ghost btn-sm btn-circle"
          title="返回导入日报"
          @click="goBackToImport"
        >
          <span class="material-symbols-outlined">arrow_back</span>
        </button>
        <div>
          <h2 class="text-xl font-semibold text-base-content flex items-center gap-2">
            <span class="material-symbols-outlined text-primary icon-lg">auto_awesome</span>
            AI 生成解析配置
          </h2>
          <p class="text-sm text-fg-subtle">
            上传施工日报，与 AI 对话生成解析配置（AI 仅使用受控工具，不访问文件系统）
          </p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="isStreaming" class="text-xs text-info flex items-center gap-1">
          <span class="loading loading-spinner loading-xs"></span>
          生成中…
        </span>
        <span
          v-if="usageData && usageData.recordCount > 0"
          class="badge badge-sm badge-neutral gap-1"
          :title="`累计 ${usageData.recordCount} 次对话 · ${usageData.totalInputTokens.toLocaleString()} in / ${usageData.totalOutputTokens.toLocaleString()} out tokens`"
        >
          <span class="material-symbols-outlined icon-xs">receipt_long</span>
          ≈ ${{ usageData.totalCost.toFixed(4) }}
        </span>
        <button
          v-if="messages.length > 0"
          class="btn btn-ghost btn-sm"
          :disabled="isStreaming"
          @click="handleClear"
        >
          <span class="material-symbols-outlined icon-sm">delete_sweep</span>
          <span>清空对话</span>
        </button>
      </div>
    </div>

    <!-- 配置保存成功横幅 -->
    <div v-if="configSaved" class="alert alert-success flex flex-wrap gap-2" role="alert">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined icon-sm">check_circle</span>
        <span>解析配置已成功保存，可直接用它解析日报</span>
      </div>
      <button class="btn btn-success btn-sm ml-auto" @click="goBackToImport">
        <span class="material-symbols-outlined icon-sm">upload_file</span>
        <span>去导入日报解析</span>
      </button>
    </div>

    <!-- 聊天主体 -->
    <div class="panel flex-1 min-h-0 flex flex-col">
      <!-- 消息区 -->
      <div class="flex-1 overflow-y-auto p-4 space-y-4">
        <!-- 空状态 -->
        <div
          v-if="messages.length === 0"
          class="h-full flex flex-col items-center justify-center gap-4 text-center"
        >
          <div class="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
            <span class="material-symbols-outlined icon-2xl text-primary">chat</span>
          </div>
          <div>
            <p class="text-base-content font-medium mb-1">开始 AI 配置会话</p>
            <p class="text-sm text-fg-subtle">
              上传日报文件后，告诉 AI 你的需求；AI 将按步骤生成、校验并保存解析配置
            </p>
          </div>
          <div class="flex flex-wrap justify-center gap-2">
            <button
              v-for="s in SUGGESTIONS"
              :key="s"
              class="btn btn-outline btn-sm"
              :disabled="isStreaming"
              @click="input = s"
            >
              {{ s }}
            </button>
          </div>
        </div>

        <!-- 消息列表 -->
        <template v-for="msg in messages" :key="msg.id">
          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" class="flex justify-end">
            <div
              class="max-w-[85%] bg-primary/10 border border-primary/20 rounded-2xl rounded-br-sm px-4 py-2.5"
            >
              <p class="text-sm text-base-content whitespace-pre-wrap">{{ msg.content }}</p>
              <div v-if="(msg.attachments?.length ?? 0) > 0" class="mt-1.5 flex flex-wrap gap-1.5">
                <span
                  v-for="name in msg.attachments"
                  :key="name"
                  class="inline-flex items-center gap-1 text-xs bg-primary/15 text-primary px-2 py-0.5 rounded-full"
                >
                  <span class="material-symbols-outlined icon-xs">description</span>
                  {{ name }}
                </span>
              </div>
            </div>
          </div>

          <!-- AI 回复 -->
          <div v-else class="flex justify-start">
            <div class="max-w-[92%] space-y-2">
              <!-- 工具调用过程（每消息至多一个 toolCall） -->
              <div
                v-if="msg.toolCall"
                class="panel panel-hover p-2.5"
                :class="{
                  'border-error/40': toolIsError(msg.toolCall),
                  'border-success/30': !toolIsError(msg.toolCall),
                }"
              >
                <div class="flex items-center gap-2 mb-1">
                  <span
                    class="w-5 h-5 rounded-md flex items-center justify-center"
                    :class="toolIsError(msg.toolCall) ? 'bg-error/10' : 'bg-primary/10'"
                  >
                    <span
                      class="material-symbols-outlined icon-sm"
                      :class="toolIsError(msg.toolCall) ? 'text-error' : 'text-primary'"
                    >
                      {{ toolIsError(msg.toolCall) ? 'error' : 'construction' }}
                    </span>
                  </span>
                  <span class="text-sm font-medium text-base-content">
                    {{ toolLabel(msg.toolCall.name) }}
                  </span>
                  <span
                    v-if="toolIsRunning(msg.toolCall)"
                    class="text-xs text-info flex items-center gap-1 ml-auto"
                  >
                    <span class="loading loading-spinner loading-xs"></span>
                    执行中
                  </span>
                  <span v-else-if="toolIsError(msg.toolCall)" class="text-xs text-error ml-auto">
                    失败
                  </span>
                  <span v-else class="text-xs text-success ml-auto">完成</span>
                </div>
                <p
                  v-if="summarizeArgs(msg.toolCall.args)"
                  class="text-xs text-fg-subtle font-mono truncate"
                >
                  {{ summarizeArgs(msg.toolCall.args) }}
                </p>
                <p
                  v-if="msg.toolCall.result"
                  class="text-xs text-fg-subtle mt-1 whitespace-pre-wrap line-clamp-3"
                >
                  {{ resultSummary(msg.toolCall) }}
                </p>
              </div>

              <!-- AI 叙述气泡（每条消息最多一个 toolCall；纯工具/回显消息无叙述气泡） -->
              <div
                v-if="msg.text"
                class="bg-base-200/60 border border-base-300 rounded-2xl rounded-bl-sm px-4 py-2.5"
              >
                <MarkdownStream
                  class="ai-markdown"
                  :content="msg.text"
                  :final="msg.status === 'done' || msg.status === 'error'"
                  @reveal="handleReveal"
                />
              </div>

              <!-- 无叙述且仍在思考（尚未产出 delta）→ 提示占位 -->
              <div
                v-else-if="msg.status === 'streaming' && !msg.toolCall"
                class="bg-base-200/60 border border-base-300 rounded-2xl rounded-bl-sm px-4 py-2.5 flex items-center gap-2 text-sm text-fg-subtle"
              >
                <span class="loading loading-dots loading-sm"></span>
                <span>AI 正在思考…</span>
              </div>

              <!-- 错误提示（无论是否带叙述都展示） -->
              <div
                v-if="msg.status === 'error' && msg.error"
                class="alert alert-error alert-sm"
                role="alert"
              >
                <span class="material-symbols-outlined icon-sm">error</span>
                <span>{{ msg.error }}</span>
              </div>
            </div>
          </div>
        </template>
        <div ref="scrollAnchor"></div>
      </div>

      <!-- 输入区 -->
      <div class="border-t border-base-300 p-3 space-y-2">
        <!-- 已选附件 -->
        <div v-if="selectedFiles.length" class="flex flex-wrap gap-2">
          <span
            v-for="(file, fi) in selectedFiles"
            :key="`${file.name}-${fi}`"
            class="inline-flex items-center gap-1.5 text-xs bg-base-200 border border-base-300 rounded-full pl-2 pr-1 py-0.5"
          >
            <span class="material-symbols-outlined icon-sm text-fg-subtle">description</span>
            <span class="max-w-40 truncate">{{ file.name }}</span>
            <button class="btn btn-ghost btn-xs btn-circle" @click="removeFile(fi)">
              <span class="material-symbols-outlined icon-xs">close</span>
            </button>
          </span>
        </div>

        <div class="flex items-end gap-2">
          <button
            class="btn btn-ghost btn-square"
            :disabled="isStreaming"
            title="上传日报文件"
            @click="pickFile"
          >
            <span class="material-symbols-outlined">attach_file</span>
          </button>
          <textarea
            v-model="input"
            class="input flex-1 min-h-10 max-h-32 resize-y py-2"
            rows="1"
            :placeholder="projectReady ? '输入需求，或先上传日报文件…' : '项目上下文不可用'"
            :disabled="!projectReady"
            @keydown.enter.exact.prevent="handleSend"
          ></textarea>
          <button
            v-if="isStreaming"
            class="btn btn-error btn-square"
            title="停止生成"
            @click="handleStop"
          >
            <span class="material-symbols-outlined">stop</span>
          </button>
          <button
            v-else
            class="btn btn-primary btn-square"
            :disabled="!canSend"
            title="发送"
            @click="handleSend"
          >
            <span class="material-symbols-outlined">send</span>
          </button>
        </div>
      </div>
    </div>

    <input
      ref="fileInput"
      type="file"
      class="hidden"
      accept=".xlsx,.xls,.csv"
      multiple
      @change="handleFileChange"
    />
  </div>
</template>
