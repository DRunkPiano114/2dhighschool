import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import type { Meta, SceneIndexEntry, Emotion } from '../../lib/types'
import { loadMeta, loadScenes } from '../../lib/data'
import { SEAT_LAYOUT, EMOTION_COLORS } from '../../lib/constants'
import { Blackboard } from './Blackboard'
import { SeatCard } from './SeatCard'
import { SceneTimeline } from './SceneTimeline'

export function SeatMap() {
  const navigate = useNavigate()
  const [meta, setMeta] = useState<Meta | null>(null)
  const [scenes, setScenes] = useState<SceneIndexEntry[]>([])
  const [hoveredAgent, setHoveredAgent] = useState<string | null>(null)

  useEffect(() => {
    loadMeta().then((m) => {
      setMeta(m)
      const latestDay = m.days[m.days.length - 1]
      if (latestDay) {
        loadScenes(latestDay).then(setScenes).catch(() => {})
      }
    })
  }, [])

  if (!meta) {
    return (
      <div className="text-center py-20">
        <div className="inline-block w-6 h-6 border-2 border-amber border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  // Build seat → agent mapping
  const seatToAgent = new Map<number, { id: string; name: string; emotion: Emotion; position: string | null }>()
  let teacher: { id: string; name: string } | null = null

  for (const [id, agent] of Object.entries(meta.agents)) {
    if (agent.role === 'homeroom_teacher') {
      teacher = { id, name: agent.name }
    } else if (agent.seat_number) {
      seatToAgent.set(agent.seat_number, {
        id,
        name: agent.name,
        emotion: 'neutral' as Emotion, // Will be updated from trajectory
        position: agent.position,
      })
    }
  }

  const latestDay = meta.days[meta.days.length - 1] ?? 'day_001'
  const dayNum = latestDay.replace('day_', '')

  return (
    <div>
      <Blackboard currentDate={meta.current_date} examCountdown={meta.next_exam_in_days} />

      {/* Teacher */}
      {teacher && (
        <div className="flex justify-center mt-4 mb-2">
          <button
            onClick={() => navigate(`/character/${teacher!.id}`)}
            className="px-4 py-2 rounded-lg bg-white border border-gray-100 hover:border-amber/50 shadow-sm transition-colors flex items-center gap-2"
          >
            <span className="w-8 h-8 rounded-full bg-amber/20 flex items-center justify-center text-sm font-medium text-amber">
              {teacher.name[0]}
            </span>
            <span className="text-sm font-medium">{teacher.name}</span>
            <span className="text-xs text-ink-light">班主任</span>
          </button>
        </div>
      )}

      {/* Classroom grid */}
      <div className="mt-4 grid grid-cols-5 gap-3 max-w-lg mx-auto">
        {Array.from({ length: 20 }, (_, i) => {
          const seatNum = i + 1
          const agent = seatToAgent.get(seatNum)
          const pos = SEAT_LAYOUT[seatNum]

          if (!agent) {
            return (
              <div
                key={seatNum}
                className="aspect-square rounded-lg border-2 border-dashed border-gray-200 flex items-center justify-center opacity-30"
                style={{ gridRow: pos.row + 1, gridColumn: pos.col + 1 }}
              >
                <span className="text-xs text-ink-light">{seatNum}</span>
              </div>
            )
          }

          const color = EMOTION_COLORS[agent.emotion]

          return (
            <div
              key={seatNum}
              className="relative"
              style={{ gridRow: pos.row + 1, gridColumn: pos.col + 1 }}
              onMouseEnter={() => setHoveredAgent(agent.id)}
              onMouseLeave={() => setHoveredAgent(null)}
            >
              <button
                onClick={() => navigate(`/character/${agent.id}`)}
                className="w-full aspect-square rounded-lg bg-white border border-gray-100 hover:border-teal/50 shadow-sm transition-all hover:shadow-md flex flex-col items-center justify-center gap-1"
              >
                <div
                  className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-medium shadow-sm"
                  style={{ backgroundColor: color }}
                >
                  {agent.name[0]}
                </div>
                <span className="text-xs font-medium truncate w-full text-center px-1">
                  {agent.name}
                </span>
                {agent.position && (
                  <span className="text-[10px] text-amber truncate">{agent.position}</span>
                )}
              </button>

              <AnimatePresence>
                {hoveredAgent === agent.id && (
                  <SeatCard
                    agentId={agent.id}
                    agent={meta.agents[agent.id]}
                    emotion={agent.emotion}
                  />
                )}
              </AnimatePresence>
            </div>
          )
        })}
      </div>

      {/* Scene timeline */}
      <SceneTimeline
        schedule={meta.schedule}
        scenes={scenes}
        dayId={dayNum}
      />
    </div>
  )
}
