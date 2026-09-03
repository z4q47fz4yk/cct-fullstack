import { computed, ref } from 'vue'

/**
 * AI 对话 SSE 流式解析。
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
 * 该 composable 管理一次对话的状态机（session、增量文本、工具过程列表），
 * 并负责把附件 base64 化后随消息提交。
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
  /** 流式增量文本（临时缓冲） */
  streamingText: string
  /** 最终文本（message_text 事件） */
  finalText: string
  toolCalls: ChatToolCall[]
  toolResults: ChatToolResult[]
  status: 'streaming' | 'done' | 'error'
  error: string
}

export interface AiChatOptions {
  /** 会话 ID；复用同一窗口上下文 */
  sessionId?: string
  message: string
  attachments?: File[]
  /** 网络请求 AbortSignal（用于停止生成） */
  signal?: AbortSignal
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

let turnSeq = 0

export function useAiChat() {
  const sessionId = ref<string | null>(null)
  const turns = ref<ChatTurn[]>([])
  const isStreaming = ref(false)
  const activeTurnId = ref<string | null>(null)

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
        break
      case 'message_text':
        turn.finalText = (payload.text as string) ?? ''
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
    const turn: ChatTurn = {
      id: `turn-${++turnSeq}`,
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

    const attachmentPayload = []
    for (const file of options.attachments ?? []) {
      const contentBase64 = await toBase64(file)
      attachmentPayload.push({ file_name: file.name, content_base64: contentBase64 })
    }

    const body = {
      session_id: options.sessionId ?? sessionId.value,
      message: options.message,
      attachments: attachmentPayload,
    }

    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
        signal: options.signal,
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
      if (options.signal?.aborted) {
        turn.status = 'done'
        turn.error = '已停止生成'
      } else {
        turn.status = 'error'
        turn.error = e instanceof Error ? e.message : String(e)
      }
    } finally {
      isStreaming.value = false
      activeTurnId.value = null
    }
    return turn
  }

  function clear() {
    turns.value = []
    sessionId.value = null
    isStreaming.value = false
    activeTurnId.value = null
  }

  return {
    sessionId,
    turns,
    isStreaming,
    activeTurn,
    send,
    clear,
  }
}
