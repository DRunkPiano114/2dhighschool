import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useWorldStore } from '../../stores/useWorldStore'
import { EMOTION_EMOJIS, EMOTION_LABELS } from '../../lib/constants'
import { getAgentColor } from '../world/CharacterSprite'
import type { Emotion, MindState } from '../../lib/types'
import type { Focal } from './focal'

interface FocalCardProps {
  focal: Focal
  speakerName: string
  targetName?: string
  mind?: MindState
  tickIdx: number
}

export function FocalCard({ focal, speakerName, targetName, mind, tickIdx }: FocalCardProps) {
  const setFocusedAgent = useWorldStore(s => s.setFocusedAgent)

  // First mount gets a longer 400ms intro; subsequent tick swaps (key change)
  // animate in 200ms — keeps manual nav snappy without losing the entrance.
  const hasMountedRef = useRef(false)
  useEffect(() => { hasMountedRef.current = true }, [])
  const duration = hasMountedRef.current ? 0.2 : 0.4

  const emotion: Emotion | undefined = mind?.emotion
  const emoji = emotion ? EMOTION_EMOJIS[emotion] : null
  const emotionLabel = emotion ? EMOTION_LABELS[emotion] : null
  const color = `#${getAgentColor(focal.agentId).toString(16).padStart(6, '0')}`

  const badgeLabel = focal.kind === 'speaker'
    ? '说'
    : focal.kind === 'non_verbal'
      ? '动作'
      : '观察'
  const badgeTone = focal.kind === 'speaker'
    ? 'bg-amber-500/25 text-amber-200'
    : focal.kind === 'non_verbal'
      ? 'bg-rose-500/25 text-rose-200'
      : 'bg-white/10 text-white/60'

  return (
    <motion.div
      key={`${tickIdx}-${focal.agentId}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration, ease: 'easeOut' }}
      className="mx-4 my-2 rounded-lg bg-white/[0.04] border border-white/5 px-4 py-3"
    >
      <div className="flex items-center gap-2 mb-1.5 text-sm">
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${badgeTone}`}>
          [{badgeLabel}]
        </span>
        <button
          onClick={() => setFocusedAgent(focal.agentId)}
          className="font-semibold hover:underline"
          style={{ color }}
        >
          {speakerName}
        </button>
        {targetName && focal.kind === 'speaker' && (
          <>
            <span className="text-white/30">→</span>
            <span className="text-white/70">{targetName}</span>
          </>
        )}
        {emoji && (
          <span className="ml-auto text-sm text-white/60">
            {emoji} <span className="text-xs text-white/40">{emotionLabel}</span>
          </span>
        )}
      </div>

      {focal.kind === 'speaker' && focal.content && (
        <div
          className="rounded-md px-3 py-2 text-[15px] leading-relaxed"
          style={{ background: '#faf3e0', color: '#2c2c2c', border: '1px solid #e0d5c0' }}
        >
          "{focal.content}"
        </div>
      )}

      {focal.kind === 'non_verbal' && focal.content && (
        <div className="text-[14px] italic text-white/80 leading-relaxed">
          {focal.content}
        </div>
      )}

      {focal.kind === 'observation' && focal.content && (
        <div className="text-[14px] text-white/70 italic leading-relaxed font-serif">
          {focal.content}
        </div>
      )}

      {mind?.inner_thought && focal.kind !== 'observation' && (
        <div className="mt-2 text-[13px] text-[color:var(--thought-text,#c0b0d8)] italic leading-relaxed font-serif flex items-start gap-1.5">
          <span className="opacity-60">💭</span>
          <span>{mind.inner_thought}</span>
        </div>
      )}
    </motion.div>
  )
}
