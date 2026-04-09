import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useWorldStore } from '../../stores/useWorldStore'
import { streamGodModeChat, type ChatMessage } from '../../lib/chat'
import { getAgentColor } from '../world/CharacterSprite'

/** Extract day number from 'day_001' format. */
function dayNum(dayStr: string): number {
  return parseInt(dayStr.replace('day_', ''), 10) || 1
}

/** Get a time period from the current scene. */
function useTimePeriod(): string {
  const scenes = useWorldStore((s) => s.scenes)
  const sceneIndex = useWorldStore((s) => s.currentSceneIndex)
  return scenes[sceneIndex]?.time ?? '08:45'
}

export function GodModeChat() {
  const chatMode = useWorldStore((s) => s.chatMode)
  const agentId = useWorldStore((s) => s.focusedAgent)
  const meta = useWorldStore((s) => s.meta)
  const currentDay = useWorldStore((s) => s.currentDay)
  const chatMessages = useWorldStore((s) => s.chatMessages)
  const chatStreaming = useWorldStore((s) => s.chatStreaming)
  const chatStreamBuffer = useWorldStore((s) => s.chatStreamBuffer)
  const closeChat = useWorldStore((s) => s.closeChat)
  const appendChatMessage = useWorldStore((s) => s.appendChatMessage)
  const setChatStreaming = useWorldStore((s) => s.setChatStreaming)
  const appendStreamToken = useWorldStore((s) => s.appendStreamToken)
  const flushStreamBuffer = useWorldStore((s) => s.flushStreamBuffer)

  const timePeriod = useTimePeriod()
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const isOpen = chatMode === 'god' && agentId !== null
  const agentName = meta?.agents[agentId ?? '']?.name ?? agentId ?? ''
  const day = dayNum(currentDay)

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, chatStreamBuffer])

  // Focus input when opened
  useEffect(() => {
    if (isOpen) inputRef.current?.focus()
  }, [isOpen])

  const handleSend = useCallback(async () => {
    if (!input.trim() || chatStreaming || !agentId) return
    const message = input.trim()
    setInput('')

    // Add user message
    appendChatMessage({ role: 'user', content: message })
    setChatStreaming(true)

    try {
      const history: ChatMessage[] = chatMessages.map((m) => ({
        role: m.role,
        content: m.content,
        agent_name: m.agent_name,
      }))

      for await (const token of streamGodModeChat({
        agent_id: agentId,
        day,
        time_period: timePeriod,
        message,
        history,
      })) {
        appendStreamToken(token)
      }
    } catch (err) {
      appendChatMessage({
        role: 'system',
        content: `Error: ${err instanceof Error ? err.message : 'Unknown error'}`,
      })
    } finally {
      flushStreamBuffer()
      setChatStreaming(false)
    }
  }, [input, chatStreaming, agentId, chatMessages, day, timePeriod,
      appendChatMessage, setChatStreaming, appendStreamToken, flushStreamBuffer])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ x: 320, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 320, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className="fixed right-0 top-0 bottom-0 w-80 z-50 flex flex-col"
          style={{
            background: 'rgba(15, 15, 25, 0.95)',
            backdropFilter: 'blur(12px)',
          }}
        >
          {/* Header */}
          <div className="flex items-center gap-3 p-4 border-b border-white/10">
            <div
              className="w-8 h-8 rounded-full shrink-0"
              style={{ backgroundColor: '#' + getAgentColor(agentId ?? '').toString(16).padStart(6, '0') }}
            />
            <div className="flex-1">
              <div className="text-white font-semibold">{agentName}</div>
              <div className="text-xs text-gray-400">内心独白</div>
            </div>
            <button
              onClick={closeChat}
              className="text-gray-400 hover:text-white text-xl px-2"
            >
              ×
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] px-3 py-2 rounded-lg text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-blue-600/80 text-white'
                      : msg.role === 'system'
                        ? 'bg-red-900/40 text-red-300 text-xs'
                        : 'bg-white/5 text-gray-200'
                  }`}
                  style={msg.role !== 'user' && msg.role !== 'system' ? {
                    fontFamily: '"LXGW WenKai", serif',
                    fontStyle: 'italic',
                  } : undefined}
                >
                  {msg.content}
                </div>
              </div>
            ))}

            {/* Streaming buffer */}
            {chatStreamBuffer && (
              <div className="flex justify-start">
                <div
                  className="max-w-[85%] px-3 py-2 rounded-lg text-sm leading-relaxed bg-white/5 text-gray-200"
                  style={{ fontFamily: '"LXGW WenKai", serif', fontStyle: 'italic' }}
                >
                  {chatStreamBuffer}
                  <span className="animate-pulse">|</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-3 border-t border-white/10">
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="问问ta在想什么..."
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
      )}
    </AnimatePresence>
  )
}
