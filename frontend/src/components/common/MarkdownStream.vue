<script setup lang="ts">
import MarkdownRender from 'markstream-vue'
import { onBeforeUnmount, ref, watch } from 'vue'
import { useTheme } from '@/composables/useTheme'

/**
 * AI 回复的 Markdown 流式渲染封装（rAF 驱动打字机式渐进 reveal）。
 *
 * 背景：SSE 的 message_delta 可能突发成批到达，且 pi 的 message_text 会携带
 * 权威全文。若把每一帧拿到的内容整段丢给渲染器，用户看到的是“一次性全部
 * 出现”。这里在渲染层做 rAF 节流：
 *
 *  - 内部维护 revealed（已交给 markstream 的文本）与 pending（未展示缓冲）；
 *  - content 变化时若为增量（前缀一致）只并入尾部，若被权威全文替换则保留
 *    公共前缀、差异重新 reveal —— 避免 message_text 造成整段闪跳；
 *  - 每帧释放至多 CHARS_PER_FRAME 个字符，形成稳定的打字节奏，与网络到达
 *    节拍解耦；
 *  - final 到达时立即 flush 剩余缓冲（不再逐帧），并把 final 透传给渲染器
 *    收敛未闭合的代码块/表格；恢复的历史轮次以 final=true 挂载 ⇒ 整段即时显示。
 *
 * markstream 侧：smooth-streaming 关闭（避免双重调速），由本组件的 rAF 单一路
 * 径驱动；mode="chat" 专为对话流式设计；html-policy="escape" 兜底 LLM 输出中
 * 的不可信 HTML；render-code-blocks-as-pre 避免需要 stream-diffs 增强代码块。
 * 主题色由 src/assets/markstream.css 桥接到 starglass token。
 */
// Vue 3.5+ Reactive Props Destructure：解构即响应式，默认值在解构处声明。
const {
  content = '',
  /** 流是否结束（服务端 done/error 后置真） */
  final = false,
  /** 每帧最多 reveal 的字符数（越大打字越快） */
  charsPerFrame = 12,
} = defineProps<{
  content?: string
  /** 流是否结束（服务端 done/error 后置真） */
  final?: boolean
  /** 每帧最多 reveal 的字符数（越大打字越快） */
  charsPerFrame?: number
}>()

const emit = defineEmits<{
  /** 每帧 reveal 出新字符后触发（父组件据此做滚动跟随） */
  reveal: []
}>()

const { isDark } = useTheme()

/** 已交给 markstream 渲染的文本 */
const revealed = ref('')
/** 已收到但尚未展示的尾部缓冲 */
const pending = ref('')
/** 全部内容已 reveal（final 且 pending 清空后才置真，喂给渲染器 final） */
const settled = ref(false)

let rafId: number | null = null

function stopRaf() {
  if (rafId !== null) cancelAnimationFrame(rafId)
  rafId = null
}

/** 单帧 tick：把至多 charsPerFrame 个字符并入 revealed */
function tick() {
  rafId = null
  if (pending.value) {
    const take = Math.min(charsPerFrame, pending.value.length)
    revealed.value += pending.value.slice(0, take)
    pending.value = pending.value.slice(take)
    emit('reveal')
  }
  if (pending.value) {
    rafId = requestAnimationFrame(tick)
  } else if (final) {
    settled.value = true
  }
}

function syncTarget(next: string) {
  // final 已为真（如恢复的历史轮次挂载即 final）：整段即时显示，不逐帧
  if (final) {
    revealed.value = next
    pending.value = ''
    settled.value = true
    stopRaf()
    return
  }
  const cur = revealed.value
  if (next.startsWith(cur)) {
    // 常规增量（message_delta 累积 / 在已展示前缀上继续）
    pending.value = next.slice(cur.length)
  } else {
    // 内容被权威全文替换（message_text）且与已展示前缀不一致：
    // 保留公共前缀，差异部分重新 reveal，避免整段闪跳
    let i = 0
    const n = Math.min(cur.length, next.length)
    while (i < n && cur[i] === next[i]) i += 1
    revealed.value = next.slice(0, i)
    pending.value = next.slice(i)
  }
  if (pending.value && rafId === null) {
    rafId = requestAnimationFrame(tick)
  }
}

watch(
  () => content,
  (v) => syncTarget(v ?? ''),
  { immediate: true },
)

watch(
  () => final,
  (v) => {
    if (!v) return
    // 结束（或挂载即 final）：不再逐帧，把剩余缓冲一次性补完并收敛
    if (pending.value) {
      revealed.value = content
      pending.value = ''
    }
    settled.value = true
    stopRaf()
  },
  { immediate: true },
)

onBeforeUnmount(stopRaf)
</script>

<template>
  <MarkdownRender
    class="markstream-chat"
    mode="chat"
    :content="revealed"
    :final="settled"
    :is-dark="isDark"
    :smooth-streaming="false"
    :fade="false"
    :max-live-nodes="0"
    :batch-rendering="true"
    :render-batch-size="16"
    :render-batch-delay="8"
    :render-batch-budget-ms="4"
    :render-code-blocks-as-pre="true"
    html-policy="escape"
  />
</template>

<style>
/* 工程面板紧凑排版：聊天气泡内让 markstream 的字号/留白贴近全站
 * text-sm 密度（markstream 内部节点都读这些 --ms-* 排版变量）。 */
.markstream-chat {
  font-size: 0.875rem;
  line-height: 1.6;
  --ms-text-body: 0.875rem;
  --ms-leading-body: 1.6;
  --ms-text-h1: 1.25rem;
  --ms-text-h2: 1.125rem;
  --ms-text-h3: 1rem;
  --ms-text-h4: 0.9375rem;
  --ms-text-h5: 0.875rem;
  --ms-text-h6: 0.875rem;
  --ms-weight-h1: 600;
  --ms-weight-h2: 600;
  --ms-weight-h3: 600;
  --ms-weight-h4: 600;
  --ms-flow-paragraph-y: 0.625em;
  --ms-flow-list-y: 0.5em;
  --ms-flow-heading-2-mt: 1.25em;
  --ms-flow-heading-2-mb: 0.5em;
  --ms-flow-heading-3-mt: 1em;
  --ms-flow-heading-3-mb: 0.375em;
  --ms-flow-table-y: 1em;
  --ms-flow-blockquote-y: 0.875em;
  --ms-flow-codeblock-y: 0.875em;
  --ms-radius: 0.375rem;
}

/* 代码块在气泡里更紧贴面板底色，围栏过长时内部可滚动 */
.markstream-chat pre {
  max-width: 100%;
}
</style>
