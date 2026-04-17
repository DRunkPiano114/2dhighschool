import { useState } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { useWorldStore } from '../../stores/useWorldStore'
import { getAgentColor } from '../world/CharacterSprite'

function AgentPortrait({ agentId, name, selected, onClick }: {
  agentId: string
  name: string
  selected: boolean
  onClick: () => void
}) {
  const colorHex = '#' + getAgentColor(agentId).toString(16).padStart(6, '0')

  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center gap-1 p-2 rounded-lg transition-all ${
        selected ? 'bg-blue-600/40 ring-2 ring-blue-400' : 'hover:bg-white/10'
      }`}
    >
      <div className="w-10 h-10 rounded-full" style={{ backgroundColor: colorHex }} />
      <span className="text-xs text-gray-300">{name}</span>
    </button>
  )
}

interface RolePlaySetupProps {
  onClose: () => void
  initialTargetId?: string
}

export function RolePlaySetup({ onClose, initialTargetId }: RolePlaySetupProps) {
  const meta = useWorldStore((s) => s.meta)
  const openRolePlay = useWorldStore((s) => s.openRolePlayChat)
  const [userAgent, setUserAgent] = useState<string | null>(null)
  const [targets, setTargets] = useState<Set<string>>(
    () => new Set(initialTargetId ? [initialTargetId] : [])
  )

  if (!meta) return null

  const agents = Object.entries(meta.agents).filter(([, a]) => a.role !== 'homeroom_teacher')
  const allAgents = Object.entries(meta.agents)

  const toggleTarget = (id: string) => {
    const next = new Set(targets)
    if (next.has(id)) next.delete(id)
    else if (next.size < 4) next.add(id)
    setTargets(next)
  }

  const canStart = userAgent !== null && targets.size > 0

  const handleStart = () => {
    if (!canStart) return
    openRolePlay(userAgent!, [...targets])
    onClose()
  }

  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        onClick={e => e.stopPropagation()}
        className="bg-gray-900/95 border border-white/10 rounded-xl p-6 max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg text-white font-semibold">角色扮演</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">×</button>
        </div>

        {/* Step 1: Pick your character */}
        <div className="mb-4">
          <h3 className="text-sm text-gray-400 mb-2">选择你要扮演的角色</h3>
          <div className="grid grid-cols-5 gap-1">
            {agents.map(([id, a]) => (
              <AgentPortrait
                key={id}
                agentId={id}
                name={a.name}
                selected={userAgent === id}
                onClick={() => {
                  setUserAgent(id)
                  // Remove from targets if selected
                  const next = new Set(targets)
                  next.delete(id)
                  setTargets(next)
                }}
              />
            ))}
          </div>
        </div>

        {/* Step 2: Pick who to talk to */}
        {userAgent && (
          <div className="mb-4">
            <h3 className="text-sm text-gray-400 mb-2">选择对话对象（1-4人）</h3>
            <div className="grid grid-cols-5 gap-1">
              {allAgents
                .filter(([id]) => id !== userAgent)
                .map(([id, a]) => (
                  <AgentPortrait
                    key={id}
                    agentId={id}
                    name={a.name}
                    selected={targets.has(id)}
                    onClick={() => toggleTarget(id)}
                  />
                ))}
            </div>
          </div>
        )}

        {/* Start button */}
        <button
          onClick={handleStart}
          disabled={!canStart}
          className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium transition-colors"
        >
          开始对话
        </button>
      </motion.div>
    </motion.div>,
    document.body,
  )
}
