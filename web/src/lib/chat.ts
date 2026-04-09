/**
 * Chat API client — SSE streaming for God Mode and Role Play.
 */

export interface ChatMessage {
  role: string
  content: string
  agent_name?: string
}

export interface GodModeChatRequest {
  agent_id: string
  day: number
  time_period: string
  message: string
  history: ChatMessage[]
}

export interface RolePlayChatRequest {
  user_agent_id: string
  target_agent_ids: string[]
  day: number
  time_period: string
  message: string
  history: ChatMessage[]
}

export interface AgentReaction {
  agent_id: string
  agent_name: string
  action: string
  target?: string
  content: string
  inner_thought: string
  emotion: string
}

/**
 * Stream God Mode chat — yields text tokens one at a time.
 */
export async function* streamGodModeChat(req: GodModeChatRequest): AsyncGenerator<string> {
  const response = await fetch('/api/god-mode/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status}`)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Parse SSE events from buffer
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? '' // Keep incomplete last line

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (!data) continue

      try {
        const event = JSON.parse(data)
        if (event.done) return
        if (event.error) throw new Error(event.error)
        if (event.token) yield event.token
      } catch {
        // Skip unparseable lines
      }
    }
  }
}

/**
 * Stream Role Play chat — yields AgentReaction objects as they arrive.
 */
export async function* streamRolePlayChat(req: RolePlayChatRequest): AsyncGenerator<AgentReaction | { thinking: true; agent_ids: string[] }> {
  const response = await fetch('/api/role-play/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status}`)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (!data) continue

      try {
        const event = JSON.parse(data)
        if (event.done) return
        if (event.error) throw new Error(event.error)
        if (event.thinking) yield { thinking: true as const, agent_ids: event.agent_ids }
        else if (event.agent_id) yield event as AgentReaction
      } catch {
        // Skip unparseable lines
      }
    }
  }
}
