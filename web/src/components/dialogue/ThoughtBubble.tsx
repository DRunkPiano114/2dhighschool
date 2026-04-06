import { motion } from 'framer-motion'
import type { MindState } from '../../lib/types'
import { EMOTION_COLORS, EMOTION_LABELS } from '../../lib/constants'

interface ThoughtBubbleProps {
  agentName: string
  mind: MindState
  index: number
}

export function ThoughtBubble({ agentName, mind, index }: ThoughtBubbleProps) {
  const color = EMOTION_COLORS[mind.emotion] ?? '#B8B8B8'
  const label = EMOTION_LABELS[mind.emotion] ?? mind.emotion

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -4, scale: 0.95 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
      className="thought-cloud ml-11"
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-xs text-ink-light">{agentName} 的内心</span>
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs"
          style={{ backgroundColor: color + '20', color }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
          {label}
        </span>
      </div>
      <p className="font-hand text-sm leading-relaxed text-ink/80">
        {mind.inner_thought}
      </p>
    </motion.div>
  )
}
