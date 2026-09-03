<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useProjectContext } from '@/composables/useProjectContext'
import { useAiChat, type ChatTurn } from '@/composables/useAiChat'

definePage({
  meta: {
    title: 'AI 解析配置',
    icon: 'auto_awesome',
    showInNav: true,
    parentName: '/project/[projectId]/daily-report',
    navOrder: 0,
  },
})

const { currentProjectId } = useProjectContext()

const { sessionId, turns, isStreaming, send, clear } = useAiChat()

const input = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFiles = ref<File[]>([])
const abortController = ref<AbortController | null>(null)
const scrollAnchor = ref<HTMLElement | null>(null)

// 配置产出状态：任一工具结果中出现 save_report_config 成功即置真
const configSaved = ref(false)

const projectReady = computed(() => currentProjectId.value !== null)

const canSend = computed(
  () => input.value.trim().length > 0 && !isStreaming.value && projectReady.value,
)

watch(
  () => turns.value.map((t) => t.streamingText + t.finalText).join(''),
  async () => {
    await nextTick()
    scrollAnchor.value?.scrollIntoView({ behavior: 'smooth' })
  },
)

watch(
  () => turns.value.length,
  () => {
    configSaved.value = turns.value.some((t) =>
      t.toolResults.some((r) => r.tool_name === 'save_report_config' && !r.is_error),
    )
  },
)

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

function displayText(turn: ChatTurn): string {
  return turn.finalText || turn.streamingText
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

function toolResultOf(turn: ChatTurn, index: number) {
  return turn.toolResults[index]
}

function toolIsRunning(turn: ChatTurn, index: number): boolean {
  return Boolean(turn.toolCalls[index] && !turn.toolResults[index])
}

function toolIsError(turn: ChatTurn, index: number): boolean {
  return turn.toolResults[index]?.is_error === true
}

function resultSummary(turn: ChatTurn, index: number): string {
  const r = turn.toolResults[index]
  if (!r) return ''
  if (r.tool_name === 'save_report_config' && !r.is_error) {
    try {
      const parsed = JSON.parse(r.content) as { configId?: string; config_id?: string }
      const id = parsed.configId ?? parsed.config_id
      return id ? `配置已保存（ID: ${id}）` : '配置已保存'
    } catch {
      return '配置已保存'
    }
  }
  if (r.is_error) return `失败：${r.content.slice(0, 80)}`
  // 工具结果很长时截断展示
  return r.content.length > 120 ? r.content.slice(0, 120) + '…' : r.content
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

  abortController.value = new AbortController()
  try {
    await send({
      sessionId: sessionId.value ?? undefined,
      message,
      attachments: files,
      signal: abortController.value.signal,
    })
  } finally {
    abortController.value = null
  }
}

function handleStop() {
  abortController.value?.abort()
}

function handleClear() {
  clear()
  selectedFiles.value = []
  configSaved.value = false
}

const SUGGESTIONS = ['帮我根据这份日报生成解析配置', '请先查看日报结构，再编写并校验配置']
</script>

<template>
  <div class="p-6 pb-24 max-w-4xl mx-auto flex flex-col gap-4 h-[calc(100dvh-7rem)]">
    <!-- 头部 -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-semibold text-base-content flex items-center gap-2">
          <span class="material-symbols-outlined text-primary icon-lg">auto_awesome</span>
          AI 解析配置
        </h2>
        <p class="text-sm text-fg-subtle">
          上传施工日报，与 AI 对话生成日报解析配置（AI 仅使用受控工具，不访问文件系统）
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="isStreaming" class="text-xs text-info flex items-center gap-1">
          <span class="loading loading-spinner loading-xs"></span>
          生成中…
        </span>
        <button
          v-if="turns.length > 0"
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
    <div v-if="configSaved" class="alert alert-success alert-sm" role="alert">
      <span class="material-symbols-outlined icon-sm">check_circle</span>
      <span>解析配置已成功保存，可到「导入日报」步骤使用该配置解析</span>
    </div>

    <!-- 聊天主体 -->
    <div class="panel flex-1 min-h-0 flex flex-col">
      <!-- 消息区 -->
      <div class="flex-1 overflow-y-auto p-4 space-y-4">
        <!-- 空状态 -->
        <div
          v-if="turns.length === 0"
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

        <!-- 对话轮次 -->
        <template v-for="(turn, ti) in turns" :key="turn.id">
          <!-- 用户消息 -->
          <div class="flex justify-end">
            <div
              class="max-w-[85%] bg-primary/10 border border-primary/20 rounded-2xl rounded-br-sm px-4 py-2.5"
            >
              <p class="text-sm text-base-content whitespace-pre-wrap">{{ turn.message }}</p>
              <div v-if="turn.attachments.length" class="mt-1.5 flex flex-wrap gap-1.5">
                <span
                  v-for="name in turn.attachments"
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
          <div class="flex justify-start">
            <div class="max-w-[92%] space-y-2">
              <!-- 工具调用过程 -->
              <template v-for="(tool, ti2) in turn.toolCalls" :key="tool.tool_call_id">
                <div
                  class="panel panel-hover p-2.5"
                  :class="{
                    'border-error/40': toolIsError(turn, ti2),
                    'border-success/30': !toolIsError(turn, ti2),
                  }"
                >
                  <div class="flex items-center gap-2 mb-1">
                    <span
                      class="w-5 h-5 rounded-md flex items-center justify-center"
                      :class="toolIsError(turn, ti2) ? 'bg-error/10' : 'bg-primary/10'"
                    >
                      <span
                        class="material-symbols-outlined icon-sm"
                        :class="toolIsError(turn, ti2) ? 'text-error' : 'text-primary'"
                      >
                        {{ toolIsError(turn, ti2) ? 'error' : 'construction' }}
                      </span>
                    </span>
                    <span class="text-sm font-medium text-base-content">
                      {{ toolLabel(tool.tool_name) }}
                    </span>
                    <span
                      v-if="toolIsRunning(turn, ti2)"
                      class="text-xs text-info flex items-center gap-1 ml-auto"
                    >
                      <span class="loading loading-spinner loading-xs"></span>
                      执行中
                    </span>
                    <span v-else-if="toolIsError(turn, ti2)" class="text-xs text-error ml-auto">
                      失败
                    </span>
                    <span v-else class="text-xs text-success ml-auto">完成</span>
                  </div>
                  <p
                    v-if="summarizeArgs(tool.args)"
                    class="text-xs text-fg-subtle font-mono truncate"
                  >
                    {{ summarizeArgs(tool.args) }}
                  </p>
                  <p
                    v-if="toolResultOf(turn, ti2)"
                    class="text-xs text-fg-subtle mt-1 whitespace-pre-wrap line-clamp-3"
                  >
                    {{ resultSummary(turn, ti2) }}
                  </p>
                </div>
              </template>

              <!-- AI 文本 -->
              <div
                class="bg-base-200/60 border border-base-300 rounded-2xl rounded-bl-sm px-4 py-2.5"
                :class="{
                  'opacity-70': turn.status === 'streaming' && !displayText(turn),
                }"
              >
                <div v-if="displayText(turn)" class="text-sm text-base-content whitespace-pre-wrap">
                  {{ displayText(turn) }}
                </div>
                <div
                  v-else-if="turn.status === 'streaming'"
                  class="flex items-center gap-2 text-sm text-fg-subtle"
                >
                  <span class="loading loading-dots loading-sm"></span>
                  <span>AI 正在思考…</span>
                </div>
                <div
                  v-if="turn.status === 'error'"
                  class="mt-2 alert alert-error alert-sm"
                  role="alert"
                >
                  <span class="material-symbols-outlined icon-sm">error</span>
                  <span>{{ turn.error }}</span>
                </div>
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
