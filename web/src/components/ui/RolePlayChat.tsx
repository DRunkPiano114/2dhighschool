import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useWorldStore } from '../../stores/useWorldStore'
import { streamRolePlayChat, type ChatMessage } from '../../lib/chat'
import { getAgentColor } from '../world/CharacterSprite'

function dayNum(dayStr: string): number {
  return parseInt(dayStr.replace('day_', ''), 10) || 1
}

function SmallPortrait({ agentId }: { agentId: string }) {
  const colorHex = '#' + getAgentColor(agentId).toString(16).padStart(6, '0')
  return <div className="w-6 h-6 rounded-full shrink-0" style={{ backgroundColor: colorHex }} />
}

export function RolePlayChat() {
  const chatMode = useWorldStore((s) => s.chatMode)
  const meta = useWorldStore((s) => s.meta)
  const currentDay = useWorldStore((s) => s.currentDay)
  const scenes = useWorldStore((s) => s.scenes)
  const sceneIndex = useWorldStore((s) => s.currentSceneIndex)
  const userAgentId = useWorldStore((s) => s.rolePlayUserAgent)
  const targetAgentIds = useWorldStore((s) => s.rolePlayTargetAgents)
  const chatMessages = useWorldStore((s) => s.chatMessages)
  const chatStreaming = useWorldStore((s) => s.chatStreaming)
  const closeChat = useWorldStore((s) => s.closeChat)
  const appendChatMessage = useWorldStore((s) => s.appendChatMessage)
  const setChatStreaming = useWorldStore((s) => s.setChatStreaming)
  const appendAgentReaction = useWorldStore((s) => s.appendAgentReaction)

  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const isOpen = chatMode === 'roleplay' && userAgentId !== null
  const day = dayNum(currentDay)
  const timePeriod = scenes[sceneIndex]?.time ?? '08:45'
  const userName = meta?.agents[userAgentId ?? '']?.name ?? ''

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  useEffect(() => {
    if (isOpen) inputRef.current?.focus()
  }, [isOpen])

  const handleSend = useCallback(async () => {
    if (!input.trim() || chatStreaming || !userAgentId) return
    const message = input.trim()
    setInput('')

    appendChatMessage({ role: userAgentId, content: message, agent_name: userName })
    setChatStreaming(true)
    setThinking(true)

    try {
      const history: ChatMessage[] = chatMessages.map((m) => ({
        role: m.role,
        content: m.content,
        agent_name: m.agent_name,
      }))

      for await (const event of streamRolePlayChat({
        user_agent_id: userAgentId,
        target_agent_ids: targetAgentIds,
        day,
        time_period: timePeriod,
        message,
        history,
      })) {
        if ('thinking' in event) {
          setThinking(true)
        } else {
          setThinking(false)
          appendAgentReaction(event)
        }
      }
    } catch (err) {
      appendChatMessage({
        role: 'system',
        content: `Error: ${err instanceof Error ? err.message : 'Unknown error'}`,
      })
    } finally {
      setChatStreaming(false)
      setThinking(false)
    }
  }, [input, chatStreaming, userAgentId, userName, targetAgentIds, chatMessages,
      day, timePeriod, appendChatMessage, setChatStreaming, appendAgentReaction])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!isOpen || !meta) return null

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex flex-col"
      style={{ background: 'rgba(10, 10, 20, 0.98)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-3">
          {/* Participant portraits */}
          <div className="flex -space-x-2">
            <SmallPortrait agentId={userAgentId!} />
            {targetAgentIds.map((id) => (
              <SmallPortrait key={id} agentId={id} />
            ))}
          </div>
          <div>
            <span className="text-white text-sm font-medium">
              {userName} 的对话
            </span>
            <span className="text-gray-400 text-xs ml-2">
              与 {targetAgentIds.map((id) => meta.agents[id]?.name).join('、')}
            </span>
          </div>
        </div>
        <button
          onClick={closeChat}
          className="text-gray-400 hover:text-white text-sm px-3 py-1 bg-white/5 rounded hover:bg-white/10 transition-colors"
        >
          退出
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {chatMessages.map((msg, i) => {
          const isUser = msg.role === userAgentId
          const isSystem = msg.role === 'system'
          const agentName = msg.agent_name ?? meta.agents[msg.role]?.name ?? msg.role

          return (
            <div key={i} className={`flex gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
              {!isSystem && (
                <div className="shrink-0 mt-1">
                  <SmallPortrait agentId={msg.role} />
                </div>
              )}
              <div className={`max-w-[70%] ${isUser ? 'text-right' : ''}`}>
                {!isUser && !isSystem && (
                  <div className="text-xs text-gray-500 mb-1">{agentName}</div>
                )}
                <div
                  className={`inline-block px-3 py-2 rounded-lg text-sm leading-relaxed ${
                    isUser
                      ? 'bg-blue-600/80 text-white'
                      : isSystem
                        ? 'bg-red-900/40 text-red-300 text-xs'
                        : 'bg-white/8 text-gray-200'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            </div>
          )
        })}

        {/* Thinking indicator */}
        {thinking && (
          <div className="flex gap-2 items-center text-gray-400 text-sm">
            <div className="flex -space-x-1">
              {targetAgentIds.map((id) => (
                <SmallPortrait key={id} agentId={id} />
              ))}
            </div>
            <span className="animate-pulse">正在思考...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-white/10">
        <div className="flex gap-2 items-center">
          <span className="text-xs text-gray-500 shrink-0">{userName}：</span>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="说点什么..."
            disabled={chatStreaming}
            className="flex-1 bg-white/10 text-white text-sm rounded-lg px-3 py-2 outline-none placeholder-gray-500 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={chatStreaming || !input.trim()}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm px-4 py-2 rounded-lg transition-colors"
          >
            发送
          </button>
        </div>
      </div>
    </motion.div>
  )
}
