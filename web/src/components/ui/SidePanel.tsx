import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useWorldStore } from '../../stores/useWorldStore'
import { loadAgent } from '../../lib/data'
import { EMOTION_COLORS, EMOTION_LABELS } from '../../lib/constants'
import { getAgentColor } from '../world/CharacterSprite'
import type { Agent, Emotion } from '../../lib/types'

export function SidePanel() {
  const agentId = useWorldStore(s => s.focusedAgent)
  const isOpen = useWorldStore(s => s.sidePanelOpen)
  const close = useWorldStore(s => s.setSidePanelOpen)
  const [agent, setAgent] = useState<Agent | null>(null)

  useEffect(() => {
    if (!agentId) { setAgent(null); return }
    loadAgent(agentId).then(setAgent).catch(() => setAgent(null))
  }, [agentId])

  return (
    <AnimatePresence>
      {isOpen && agent && (
        <motion.div
          initial={{ x: 320, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 320, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className="absolute right-0 top-0 bottom-0 z-40 w-80 bg-gray-900/90 backdrop-blur-md border-l border-white/10 overflow-y-auto pointer-events-auto"
        >
          {/* Header */}
          <div className="sticky top-0 bg-gray-900/80 backdrop-blur-sm px-4 py-3 flex items-center justify-between border-b border-white/10">
            <div className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-full"
                style={{ background: `#${getAgentColor(agent.agent_id).toString(16).padStart(6, '0')}` }}
              />
              <span className="text-white font-medium">{agent.name}</span>
              <span className="text-white/40 text-xs">{agent.role === 'homeroom_teacher' ? '班主任' : '学生'}</span>
            </div>
            <button
              onClick={() => close(false)}
              className="text-white/40 hover:text-white/70 text-sm"
            >
              ✕
            </button>
          </div>

          <div className="px-4 py-3 space-y-4">
            {/* Emotion */}
            <Section title="情绪">
              <EmotionBar emotion={agent.state.emotion} />
            </Section>

            {/* Personality */}
            <Section title="性格">
              <div className="flex flex-wrap gap-1">
                {agent.personality.map((t, i) => (
                  <span key={i} className="px-2 py-0.5 bg-white/10 rounded-full text-xs text-white/70">{t}</span>
                ))}
              </div>
            </Section>

            {/* Academics */}
            <Section title="学业">
              <div className="text-xs text-white/60 space-y-1">
                <div>排名: <span className="text-amber-400">{agent.academics.overall_rank}</span></div>
                <div>优势: {agent.academics.strengths.join(', ')}</div>
                <div>短板: {agent.academics.weaknesses.join(', ')}</div>
              </div>
            </Section>

            {/* Concerns */}
            {agent.state.active_concerns.length > 0 && (
              <Section title="牵挂">
                <div className="space-y-1.5">
                  {agent.state.active_concerns.slice(0, 5).map((c, i) => (
                    <div key={i} className="text-xs text-white/60 flex items-start gap-1.5">
                      <IntensityDot intensity={c.intensity} />
                      <span>{c.text}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Relationships */}
            <Section title="关系">
              <div className="flex flex-wrap gap-1">
                {Object.values(agent.relationships).map(r => {
                  const color = r.favorability > 0 ? 'bg-emerald-500/30 text-emerald-300'
                    : r.favorability < 0 ? 'bg-red-500/30 text-red-300'
                    : 'bg-white/10 text-white/50'
                  return (
                    <span key={r.target_id} className={`px-2 py-0.5 rounded-full text-xs ${color}`}>
                      {r.target_name} {r.favorability > 0 ? '+' : ''}{r.favorability}
                    </span>
                  )
                })}
              </div>
            </Section>

            {/* Recent thoughts */}
            <Section title="最近想法">
              <div className="space-y-1.5">
                {agent.key_memories.slice(-5).reverse().map((m, i) => (
                  <div key={i} className="text-xs text-white/50 border-l-2 border-white/10 pl-2">
                    {m.text}
                  </div>
                ))}
              </div>
            </Section>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-white/30 text-[10px] uppercase tracking-widest mb-1.5">{title}</div>
      {children}
    </div>
  )
}

function EmotionBar({ emotion }: { emotion: Emotion }) {
  const color = EMOTION_COLORS[emotion] ?? '#888'
  const label = EMOTION_LABELS[emotion] ?? emotion
  return (
    <div className="flex items-center gap-2">
      <div className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
      <span className="text-sm text-white/80">{label}</span>
    </div>
  )
}

function IntensityDot({ intensity }: { intensity: number }) {
  const size = Math.max(6, Math.min(10, intensity))
  const opacity = 0.4 + (intensity / 10) * 0.6
  return (
    <div
      className="rounded-full bg-amber-400 mt-1 flex-shrink-0"
      style={{ width: size, height: size, opacity }}
    />
  )
}
