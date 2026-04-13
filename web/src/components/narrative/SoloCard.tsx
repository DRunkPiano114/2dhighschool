import { useEffect, useState } from 'react'
import { useWorldStore } from '../../stores/useWorldStore'
import { EMOTION_EMOJIS, EMOTION_LABELS } from '../../lib/constants'
import { getAgentColor } from '../world/CharacterSprite'
import { loadAgent } from '../../lib/data'
import type { ActiveConcern, SoloReflection } from '../../lib/types'

interface SoloCardProps {
  agentId: string
  agentName: string
  soloReflection: SoloReflection
}

export function SoloCard({ agentId, agentName, soloReflection }: SoloCardProps) {
  const setFocusedAgent = useWorldStore(s => s.setFocusedAgent)
  const color = `#${getAgentColor(agentId).toString(16).padStart(6, '0')}`
  const emoji = EMOTION_EMOJIS[soloReflection.emotion]
  const label = EMOTION_LABELS[soloReflection.emotion]

  // Pull the top 1-2 concerns to give the lone agent some psychological texture
  // (otherwise solo scenes feel hollow). Note: this is the agent's CURRENT
  // state, not a per-scene snapshot, so very old solo scenes may show concerns
  // the agent didn't yet have. Acceptable for v1.
  const [topConcerns, setTopConcerns] = useState<ActiveConcern[]>([])
  useEffect(() => {
    let cancelled = false
    loadAgent(agentId).then(a => {
      if (cancelled) return
      const sorted = [...a.state.active_concerns].sort((x, y) => y.intensity - x.intensity)
      setTopConcerns(sorted.slice(0, 2))
    }).catch(() => {})
    return () => { cancelled = true }
  }, [agentId])

  return (
    <div className="mx-auto max-w-lg my-4 rounded-lg bg-white/[0.04] border border-white/5 px-5 py-4">
      <div className="flex items-center gap-2 text-sm mb-2">
        <span className="text-white/40 text-xs">🧘</span>
        <button
          onClick={() => setFocusedAgent(agentId)}
          className="font-semibold hover:underline"
          style={{ color }}
        >
          {agentName}
        </button>
        <span className="text-white/60">· {soloReflection.activity}</span>
        <span className="ml-auto text-white/70">
          {emoji} <span className="text-xs text-white/40">{label}</span>
        </span>
      </div>
      <div className="text-[14px] text-white/70 italic leading-relaxed font-serif">
        {soloReflection.inner_thought}
      </div>
      {topConcerns.length > 0 && (
        <div className="mt-3 pt-3 border-t border-white/5 text-xs text-white/45">
          <span className="text-white/30 mr-1.5">心里挂着</span>
          {topConcerns.map((c, i) => (
            <span key={i}>
              {i > 0 && <span className="text-white/20 mx-1.5">·</span>}
              <span className={c.positive ? 'text-emerald-300/70' : 'text-amber-300/70'}>
                {c.text}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
