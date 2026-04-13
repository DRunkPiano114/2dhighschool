import { useWorldStore } from '../../stores/useWorldStore'
import { EMOTION_EMOJIS } from '../../lib/constants'
import { getAgentColor } from '../world/CharacterSprite'
import type { MindState } from '../../lib/types'

interface ObserverRowProps {
  observers: Array<[string, MindState]>
  participantNames: Record<string, string>
}

export function ObserverRow({ observers, participantNames }: ObserverRowProps) {
  const setFocusedAgent = useWorldStore(s => s.setFocusedAgent)

  if (observers.length === 0) return null

  return (
    <div className="mx-4 my-2 max-h-full overflow-y-auto space-y-1">
      {/* sorted: is_disruptive DESC → urgency DESC — visual is intentionally
          uniform; top-row primacy is via spatial order, not visual weight */}
      {observers.map(([id, mind]) => {
        const name = participantNames[id] ?? id
        const color = `#${getAgentColor(id).toString(16).padStart(6, '0')}`
        const emoji = EMOTION_EMOJIS[mind.emotion] ?? '😐'
        return (
          <div
            key={id}
            className="flex items-start gap-2 text-[12px] leading-relaxed px-2 py-1 rounded"
            style={{ opacity: 0.7 }}
          >
            <span className="mt-0.5">{emoji}</span>
            <button
              onClick={() => setFocusedAgent(id)}
              className="font-medium hover:underline shrink-0"
              style={{ color }}
            >
              {name}
            </button>
            <span className="text-white/30 shrink-0">·</span>
            <span className="text-white/70 truncate">{mind.inner_thought}</span>
          </div>
        )
      })}
    </div>
  )
}
