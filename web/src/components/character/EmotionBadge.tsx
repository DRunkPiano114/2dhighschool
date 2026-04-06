import type { Emotion } from '../../lib/types'
import { EMOTION_COLORS, EMOTION_LABELS } from '../../lib/constants'

interface EmotionBadgeProps {
  emotion: Emotion
  size?: 'sm' | 'md'
}

export function EmotionBadge({ emotion, size = 'sm' }: EmotionBadgeProps) {
  const color = EMOTION_COLORS[emotion] ?? '#B8B8B8'
  const label = EMOTION_LABELS[emotion] ?? emotion
  const dotSize = size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2'
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm'

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full ${textSize}`}
      style={{ backgroundColor: color + '20', color }}
    >
      <span className={`${dotSize} rounded-full`} style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}
