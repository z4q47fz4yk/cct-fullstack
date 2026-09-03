import { computed, ref } from 'vue'
import { useProjectContext } from '@/composables/useProjectContext'
import { useProjectStorage } from '@/composables/useProjectStorage'

/**
 * AI 对话 SSE 流式解析 + 历史持久化。
 *
 * 后端 `/ai/chat` 返回 text/event-stream：
 * - event: start        → {session_id, attachment_paths}
 * - event: message_delta→ {delta}
 * - event: message_text → {text}
 * - event: tool_call    → {tool_call_id, tool_name, args}
 * - event: tool_result  → {tool_call_id, tool_name, content, is_error}
 * - event: done         → {}
 * - event: error        → {message}
 *
 * 历史通过 localStorage（按 project 隔离）持久化，刷新/切页后可恢复。
 */

export interface ChatToolCall {
  tool_call_id: string
  tool_name: string
  args: Record<string, unknown>
}

export interface ChatToolResult {
  tool_call_id: string
  tool_name: string
  content: string
  is_error: boolean
}

export interface ChatTurn {
  id: string
  message: string
  attachments: string[]
  /** 流式增量文本（临时缓冲；恢复历史时已并回 finalText） */
  streamingText: string
  /** 最终文本（message_text 事件） */
  finalText: string
  toolCalls: ChatToolCall[]
  toolResults: ChatToolResult[]
  status: 'streaming' | 'done' | 'error'
  error: string
}

export interface AiChatOptions {
  message: string
  attachments?: File[]
  /** 网络请求 AbortSignal（本地即时停止，随后应调 stop() 通知后端） */
  signal?: AbortSignal
}

interface ChatHistory {
  sessionId: string | null
  turns: ChatTurn[]
}

export function useAiChat() {
  const { currentProjectId } = useProjectContext()
  const projectId = computed(() => currentProjectId.value)

  // 历史持久化：localStorage，按项目隔离（ai:chat:{projectId}）
  const history = useProjectStorage<ChatHistory>('ai:chat', {
    sessionId: null,
    turns: [],
  })

  const sessionId = ref<string | null>(history.value.sessionId)
  const turns = ref<ChatTurn[]>(history.value.turns)
  const isStreaming = ref(false)
  const activeTurnId = ref<string | null>(null)
  const abortController = ref<AbortController | null>(null)

  // 恢复历史：刷新/中断残留的 streaming turn 归一为 done（不重放工具副作用）。
  // 同时本地清空其增量缓冲（已无后续 delta 会到达）。
  let restoredDirty = false
  for (const t of turns.value) {
    if (t.status === 'streaming') {
      t.status = 'done'
      t.error = t.error || '上次生成被中断，可重新发送'
      t.streamingText = ''
      restoredDirty = true
    }
  }

  // 持久化：turns/sessionId 变更时写回（流式期间高频率写 localStorage——
  // 用 debounce 避免卡顿；停止/结束时强制写一次）。
  let persistTimer: ReturnType<typeof setTimeout> | null = null
  function schedulePersist(force = false) {
    if (persistTimer) clearTimeout(persistTimer)
    const flush = () => {
      persistTimer = null
      history.value = { sessionId: sessionId.value, turns: turns.value }
    }
    if (force) flush()
    else persistTimer = setTimeout(flush, 800)
  }
  // 首次载入若修复了残留 streaming → 立即落盘
  if (restoredDirty) schedulePersist(true)

  const activeTurn = computed(() => turns.value.find((t) => t.id === activeTurnId.value) ?? null)

  function handleBlock(turn: ChatTurn, block: string) {
    const lines = block.split('\n')
    let event = 'message'
    const dataLines: string[] = []
    for (const line of lines) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (dataLines.length === 0) return
    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(dataLines.join('\n'))
    } catch {
      return
    }

    switch (event) {
      case 'start':
        sessionId.value = (payload.session_id as string) ?? null
        break
      case 'message_delta':
        turn.streamingText += (payload.delta as string) ?? ''
        schedulePersist()
        break
      case 'message_text':
        turn.finalText = (payload.text as string) ?? ''
        // 增量缓冲可清理（最终文本已落地）
        turn.streamingText = ''
        schedulePersist()
        break
      case 'tool_call':
        turn.toolCalls.push({
          tool_call_id: (payload.tool_call_id as string) ?? '',
          tool_name: (payload.tool_name as string) ?? '',
          args: (payload.args as Record<string, unknown>) ?? {},
        })
        break
      case 'tool_result': {
        const result: ChatToolResult = {
          tool_call_id: (payload.tool_call_id as string) ?? '',
          tool_name: (payload.tool_name as string) ?? '',
          content: (payload.content as string) ?? '',
          is_error: Boolean(payload.is_error),
        }
        turn.toolResults.push(result)
        break
      }
      case 'error':
        turn.status = 'error'
        turn.error = (payload.message as string) ?? '未知错误'
        break
      case 'done':
        if (turn.status !== 'error') turn.status = 'done'
        break
      default:
        break
    }
  }

  async function send(options: AiChatOptions): Promise<ChatTurn> {
    if (projectId.value == null) {
      throw new Error('项目上下文不可用')
    }
    const turn: ChatTurn = {
      id: `turn-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      message: options.message,
      attachments: options.attachments?.map((f) => f.name) ?? [],
      streamingText: '',
      finalText: '',
      toolCalls: [],
      toolResults: [],
      status: 'streaming',
      error: '',
    }
    turns.value.push(turn)
    activeTurnId.value = turn.id
    isStreaming.value = true
    schedulePersist(true)

    const attachmentPayload = []
    for (const file of options.attachments ?? []) {
      const contentBase64 = await toBase64(file)
      attachmentPayload.push({ file_name: file.name, content_base64: contentBase64 })
    }

    // 首轮 session_id 为 null 时本地生成并写回（后端沿用），
    // 保证生成期间/停止时总有会话 ID 可 abort
    if (sessionId.value == null) {
      sessionId.value = createSessionId()
    }

    const body = {
      project_id: projectId.value,
      session_id: sessionId.value,
      message: options.message,
      attachments: attachmentPayload,
    }

    abortController.value = new AbortController()
    const signal = options.signal ?? abortController.value.signal
    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
        signal,
      })
      if (!res.ok || !res.body) {
        let detail = `HTTP ${res.status}`
        try {
          const json = (await res.json()) as { detail?: string }
          if (json.detail) detail = json.detail
        } catch {
          // 非 JSON 响应，保留状态码
        }
        throw new Error(detail)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // 按空行切分 SSE 块
        let sep = buffer.indexOf('\n\n')
        while (sep >= 0) {
          const block = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          handleBlock(turn, block)
          sep = buffer.indexOf('\n\n')
        }
      }

      if (turn.status === 'streaming') {
        turn.status = 'done'
      }
    } catch (e) {
      if (signal.aborted) {
        turn.status = 'done'
        turn.error = '已停止生成'
      } else {
        turn.status = 'error'
        turn.error = e instanceof Error ? e.message : String(e)
      }
    } finally {
      isStreaming.value = false
      activeTurnId.value = null
      abortController.value = null
      schedulePersist(true)
    }
    return turn
  }

  /** 本地立即中断 fetch 流（前端即时反馈） */
  function cancelLocal() {
    abortController.value?.abort()
  }

  /** 通知后端中止 pi 生成（真正的停止：后端发 abort 给 pi 并释放） */
  async function stop(): Promise<void> {
    const pid = projectId.value
    const sid = sessionId.value
    if (pid == null || sid == null) return
    // 先本地断流
    cancelLocal()
    try {
      await fetch('/api/ai/abort', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ project_id: pid, session_id: sid }),
      })
    } catch {
      // 后端不可达也不阻断本地停止
    }
  }

  /** 清空对话（含历史） */
  function clear() {
    turns.value = []
    sessionId.value = null
    isStreaming.value = false
    activeTurnId.value = null
    abortController.value?.abort()
    abortController.value = null
    schedulePersist(true)
  }

  return {
    sessionId,
    turns,
    isStreaming,
    activeTurn,
    send,
    stop,
    cancelLocal,
    clear,
  }
}

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      // 去掉 data:...;base64, 前缀
      const comma = result.indexOf(',')
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

/** 生成会话 ID（crypto.randomUUID 可用时用之，否则回退） */
function createSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
