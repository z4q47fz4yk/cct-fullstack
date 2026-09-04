import { computed, ref } from 'vue'
import { useProjectContext } from '@/composables/useProjectContext'
import { useProjectStorage } from '@/composables/useProjectStorage'

/**
 * AI 对话 SSE 流式解析 + 历史持久化（消息模型）。
 *
 * 后端 `/ai/chat` 返回 text/event-stream：
 * - event: start        → {session_id, attachment_paths}
 * - event: message_delta→ {delta}         增量文本
 * - event: message_text → {text}          该 assistant 消息的权威全文
 * - event: tool_call    → {tool_call_id, tool_name, args}
 * - event: tool_result  → {tool_call_id, tool_name, content, is_error}
 * - event: done         → {}
 * - event: error        → {message}
 *
 * pi 事件序列里，每条「assistant 消息」最多带一次工具调用：
 *   message_delta… → message_text（本消息叙述全文）→ tool_call → tool_result
 * tool_result 之后该消息彻底结束；紧接其后的 message_text 是 pi 把工具结果
 * 「回喂给模型」的原文（即 tool_result 的 content），不应作为叙述展示——
 * 工具结果已展示在工具卡片上，这里直接跳过。之后模型继续叙述时，
 * 以新的 message_delta/message_text 开启**新的 assistant 消息**。
 *
 * 数据组织：`messages` 为角色化消息数组（「渲染者只读、SSE 接收者只写」）：
 * - user 消息：content + attachments；
 * - assistant 消息：text（叙述）+ 可选单个 toolCall（含 result）；
 * - 状态机：streaming → done/error；tool_result 立即把消息置 done。
 *
 * 关键实现点：SSE 更新一律「不可变替换」——复制出新消息对象再整体写回
 * `messages.value`，杜绝「改到闭包里的原始对象、绕过 reactive proxy」导致的
 * 模板不重渲染（此前表现为整段文本一次性出现）。
 */

export type AiRole = 'user' | 'assistant'

export interface AiToolCall {
  id: string
  name: string
  args: Record<string, unknown>
  /** tool_result.content（执行完成后才有值） */
  result?: string
  isError?: boolean
}

export interface AiMessage {
  id: string
  role: AiRole
  /** user 消息：用户输入 */
  content?: string
  /** user 消息：附件文件名 */
  attachments?: string[]
  /** assistant 消息：叙述文本（message_delta 累积；message_text 权威替换） */
  text: string
  /** assistant 消息：本消息内的工具调用（至多一个；tool_result 后闭合并落 result） */
  toolCall?: AiToolCall
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
  messages: AiMessage[]
}

export function useAiChat() {
  const { currentProjectId } = useProjectContext()
  const projectId = computed(() => currentProjectId.value)

  // 历史持久化：localStorage，按项目隔离（ai:chat:{projectId}）
  // 每次结构演进都会令旧数据无法无损迁移，统一按 legacy 处理（空会话）。
  const history = useProjectStorage<ChatHistory>('ai:chat', {
    sessionId: null,
    messages: [],
  })
  const isLegacy =
    !Array.isArray(history.value.messages) ||
    history.value.messages.some((m) => m.role === 'assistant' && 'toolCalls' in m)

  const sessionId = ref<string | null>(isLegacy ? null : history.value.sessionId)
  const messages = ref<AiMessage[]>(isLegacy ? [] : history.value.messages)
  const isStreaming = ref(false)
  const abortController = ref<AbortController | null>(null)

  // 恢复历史：刷新/中断残留的 streaming 消息归一为 done（不重放工具副作用）
  let restoredDirty = false
  if (!isLegacy) {
    for (const m of history.value.messages) {
      if (m.status === 'streaming') {
        m.status = 'done'
        m.error = m.error || '上次生成被中断，可重新发送'
        restoredDirty = true
      }
    }
  }

  // 持久化：messages/sessionId 变更时写回（流式期间高频率写 localStorage——
  // 用 debounce 避免卡顿；停止/结束时强制写一次）。
  let persistTimer: ReturnType<typeof setTimeout> | null = null
  function schedulePersist(force = false) {
    if (persistTimer) clearTimeout(persistTimer)
    const flush = () => {
      persistTimer = null
      history.value = { sessionId: sessionId.value, messages: messages.value }
    }
    if (force) flush()
    else persistTimer = setTimeout(flush, 800)
  }
  // 首次载入若修复了残留 streaming → 立即落盘
  if (restoredDirty) schedulePersist(true)

  /** 当前「可写入」的 assistant 消息：末位且仍 streaming（未因 tool_result 关闭） */
  function openAssistant(): AiMessage | null {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && last.status === 'streaming') return last
    return null
  }

  /** 新建一条 assistant 消息（返回不可变写回后的新消息引用） */
  function appendAssistant(
    init: Partial<Pick<AiMessage, 'text' | 'toolCall' | 'status' | 'error'>> = {},
  ): AiMessage {
    const msg: AiMessage = {
      id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      role: 'assistant',
      text: init.text ?? '',
      toolCall: init.toolCall,
      status: init.status ?? 'streaming',
      error: init.error ?? '',
    }
    messages.value = [...messages.value, msg]
    return msg
  }

  /** 不可变替换最后一条 assistant 消息 */
  function updateLastAssistant(updater: (m: AiMessage) => AiMessage) {
    const list = messages.value
    const last = list[list.length - 1]
    if (!last || last.role !== 'assistant') return
    const next = updater(last)
    if (!Object.is(next, last)) {
      messages.value = [...list.slice(0, -1), next]
    }
  }

  /** 结束路径兜底：有打开的 assistant 消息则关闭；否则（末位是 user）补一条 */
  function closeOpenOrAppend(status: 'done' | 'error', error: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      updateLastAssistant((m) =>
        m.status === 'streaming' ? { ...m, status, error: error || m.error } : m,
      )
    } else {
      appendAssistant({ text: '', status, error })
    }
  }

  function handleBlock(block: string) {
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

      // pi 的 assistant 叙述一定先以 message_delta 到达（「纯 message_text」是
      // 对用户输入 / 工具结果的回显，不是 AI 回复）。因此只有 message_delta
      // 有权「开启」一条 assistant 消息；message_text 只对已开启的消息做
      // 权威全文替换，绝不用它新建消息。

      case 'message_delta': {
        const delta = (payload.delta as string) ?? ''
        if (!delta) break
        const open = openAssistant()
        if (open) {
          updateLastAssistant((m) => ({ ...m, text: m.text + delta }))
        } else {
          // 上一条消息已结束（tool_result 关闭 / 无打开消息）→ 新开 assistant 消息
          appendAssistant({ text: delta })
        }
        schedulePersist()
        break
      }

      case 'message_text': {
        const text = (payload.text as string) ?? ''
        if (!text) break
        const open = openAssistant()
        // 仅在「已有 delta 开启的叙述消息」上做权威替换；
        // 无打开消息或打开的是纯工具消息 → 该 message_text 是回显，忽略。
        if (open && open.text) {
          updateLastAssistant((m) => ({ ...m, text }))
          schedulePersist()
        }
        break
      }

      case 'tool_call': {
        const call: AiToolCall = {
          id: (payload.tool_call_id as string) ?? '',
          name: (payload.tool_name as string) ?? '',
          args: (payload.args as Record<string, unknown>) ?? {},
        }
        const open = openAssistant()
        if (open && !open.toolCall) {
          // 叙述 + 工具调用同属一条消息（协议上每消息至多一个 tool_call）
          updateLastAssistant((m) => ({ ...m, toolCall: call }))
        } else {
          // 无打开消息 / 该消息已带 toolCall（协议上不可能）→ 新开一条纯工具消息
          appendAssistant({ toolCall: call })
        }
        break
      }

      case 'tool_result': {
        const id = (payload.tool_call_id as string) ?? ''
        const content = (payload.content as string) ?? ''
        const isError = Boolean(payload.is_error)
        const list = messages.value
        const last = list[list.length - 1]
        if (last && last.role === 'assistant' && last.toolCall?.id === id) {
          // 工具完成 → 本条 assistant 消息彻底结束（关闭，不再可写）。
          // 其后的回显 message_text 因无打开消息而被上面的 message_text 分支忽略。
          const next = {
            ...last,
            toolCall: { ...last.toolCall, result: content, isError },
            status: isError ? 'error' : 'done',
            error: isError ? '工具执行失败' : '',
          } as AiMessage
          messages.value = [...list.slice(0, -1), next]
        }
        schedulePersist()
        break
      }

      case 'error':
        updateLastAssistant((m) => ({
          ...m,
          status: 'error',
          error: (payload.message as string) ?? '未知错误',
        }))
        break

      case 'done':
        if (messages.value.some((m) => m.status === 'streaming')) {
          updateLastAssistant((m) => (m.status === 'error' ? m : { ...m, status: 'done' }))
        }
        break

      default:
        break
    }
  }

  async function send(options: AiChatOptions): Promise<void> {
    if (projectId.value == null) {
      throw new Error('项目上下文不可用')
    }

    // 追加 user 消息（assistant 消息由后续 SSE 事件按需创建）
    const userMessage: AiMessage = {
      id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      role: 'user',
      content: options.message,
      attachments: options.attachments?.map((f) => f.name) ?? [],
      text: '',
      status: 'done',
      error: '',
    }
    messages.value = [...messages.value, userMessage]
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
          handleBlock(block)
          sep = buffer.indexOf('\n\n')
        }
      }

      // 流结束但尚未收到 done/error → 关闭仍打开的 assistant 消息
      updateLastAssistant((m) => (m.status === 'streaming' ? { ...m, status: 'done' } : m))
    } catch (e) {
      if (signal.aborted) {
        // 用户点停止：若有打开的 assistant 消息则关闭标记；否则补一条说明消息
        closeOpenOrAppend('done', '已停止生成')
      } else {
        closeOpenOrAppend('error', e instanceof Error ? e.message : String(e))
      }
    } finally {
      isStreaming.value = false
      abortController.value = null
      schedulePersist(true)
    }
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
    messages.value = []
    sessionId.value = null
    isStreaming.value = false
    abortController.value?.abort()
    abortController.value = null
    schedulePersist(true)
  }

  return {
    sessionId,
    messages,
    isStreaming,
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
