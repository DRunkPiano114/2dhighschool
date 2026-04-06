import { motion } from 'framer-motion'
import type { AgentMeta, Emotion } from '../../lib/types'
import { EMOTION_COLORS, EMOTION_LABELS } from '../../lib/constants'

interface SeatCardProps {
  agentId: string
  agent: AgentMeta
  emotion?: Emotion
  concern?: string
  innerThought?: string
}

export function SeatCard({ agent, emotion, concern, innerThought }: SeatCardProps) {
  const e = emotion ?? 'neutral'
  const color = EMOTION_COLORS[e]
  const label = EMOTION_LABELS[e]

  return (
    <motion.div
      initial={{ opacity: 0, y: 5, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="absolute left-1/2 bottom-full mb-2 -translate-x-1/2 z-30 w-48 p-3 bg-white rounded-xl shadow-xl border border-gray-100"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="font-medium text-sm">{agent.name}</span>
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs"
          style={{ backgroundColor: color + '20', color }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
          {label}
        </span>
      </div>
      {agent.position && (
        <p className="text-xs text-amber mb-1">{agent.position}</p>
      )}
      {concern && (
        <p className="text-xs text-ink-light line-clamp-2 mb-1">💭 {concern}</p>
      )}
      {innerThought && (
        <p className="text-xs font-hand text-ink/60 line-clamp-2">"{innerThought}"</p>
      )}
      <div className="absolute left-1/2 top-full -translate-x-1/2 w-2 h-2 bg-white border-r border-b border-gray-100 rotate-45 -mt-1" />
    </motion.div>
  )
}
