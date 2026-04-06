import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import type { SceneFile, GroupData } from '../../lib/types'
import { loadSceneFile } from '../../lib/data'
import { useAppStore } from '../../stores/useAppStore'
import { EMOTION_COLORS, EMOTION_LABELS, LOCATION_ICONS } from '../../lib/constants'
import { TickBlock } from './TickBlock'
import { MindReadingToggle } from './MindReadingToggle'

function SoloCard({ group, names }: { group: GroupData; names: Record<string, string> }) {
  if (!('is_solo' in group) || !group.is_solo) return null
  const r = group.solo_reflection
  const name = names[group.participants[0]] ?? group.participants[0]
  const color = EMOTION_COLORS[r.emotion] ?? '#B8B8B8'
  const label = EMOTION_LABELS[r.emotion] ?? r.emotion

  return (
    <div className="thought-cloud max-w-md mx-auto my-6">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-full bg-teal/20 flex items-center justify-center text-sm font-medium text-teal">
          {name[0]}
        </div>
        <span className="font-medium text-sm">{name}</span>
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs"
          style={{ backgroundColor: color + '20', color }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
          {label}
        </span>
      </div>
      {r.activity && (
        <p className="text-sm text-ink-light italic mb-2">{r.activity}</p>
      )}
      <p className="font-hand text-sm leading-relaxed text-ink/80">{r.inner_thought}</p>
    </div>
  )
}

export function SceneViewer() {
  const { dayId, sceneFile } = useParams<{ dayId: string; sceneFile: string }>()
  const [scene, setScene] = useState<SceneFile | null>(null)
  const [error, setError] = useState<string | null>(null)
  const activeGroupIndex = useAppStore((s) => s.activeGroupIndex)
  const setActiveGroupIndex = useAppStore((s) => s.setActiveGroupIndex)

  useEffect(() => {
    if (!dayId || !sceneFile) return
    setScene(null)
    setError(null)
    loadSceneFile(`day_${dayId.padStart(3, '0')}`, `${sceneFile}.json`)
      .then(setScene)
      .catch(() => setError('无法加载场景数据'))
  }, [dayId, sceneFile])

  if (error) {
    return (
      <div className="text-center py-20">
        <p className="text-ink-light mb-4">{error}</p>
        <Link to="/" className="text-teal hover:underline">返回教室</Link>
      </div>
    )
  }

  if (!scene) {
    return (
      <div className="text-center py-20">
        <div className="inline-block w-6 h-6 border-2 border-amber border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const { groups, participant_names: names } = scene
  const activeGroup = groups[activeGroupIndex] ?? groups[0]
  const locationIcon = LOCATION_ICONS[scene.scene.location] ?? '📍'

  return (
    <div className="max-w-2xl mx-auto">
      {/* Scene header */}
      <div className="mb-6">
        <Link to="/" className="text-sm text-ink-light hover:text-teal transition-colors">
          ← 返回教室
        </Link>
        <div className="mt-3 flex items-center gap-3">
          <span className="text-2xl">{locationIcon}</span>
          <div>
            <h1 className="text-xl font-medium">
              {scene.scene.time} {scene.scene.name}
            </h1>
            <p className="text-sm text-ink-light">{scene.scene.description}</p>
          </div>
        </div>
      </div>

      {/* Group tabs */}
      {groups.length > 1 && (
        <div className="flex gap-2 mb-4 overflow-x-auto pb-2">
          {groups.map((g, i) => {
            const isSolo = 'is_solo' in g && g.is_solo
            const groupNames = g.participants.map((p) => names[p] ?? p)
            return (
              <button
                key={g.group_index}
                onClick={() => setActiveGroupIndex(i)}
                className={`flex-shrink-0 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  i === activeGroupIndex
                    ? 'bg-teal/15 text-teal font-medium'
                    : 'bg-white text-ink-light hover:bg-gray-50 border border-gray-100'
                }`}
              >
                {isSolo ? `${groupNames[0]}（独处）` : groupNames.join('、')}
              </button>
            )
          })}
        </div>
      )}

      {/* Group content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeGroupIndex}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
        >
          {'is_solo' in activeGroup && activeGroup.is_solo ? (
            <SoloCard group={activeGroup} names={names} />
          ) : (
            <div className="divide-y divide-gray-100">
              {(activeGroup as Extract<GroupData, { ticks: unknown[] }>).ticks.map((tick) => (
                <TickBlock key={tick.tick} tick={tick} names={names} />
              ))}
            </div>
          )}

          {/* Narrative summary at bottom (for non-solo groups) */}
          {!('is_solo' in activeGroup && activeGroup.is_solo) && (activeGroup as Extract<GroupData, { narrative: unknown }>).narrative && (
            <div className="mt-6 p-4 bg-amber/5 rounded-xl border border-amber/10">
              <h3 className="text-sm font-medium text-amber mb-2">场景小结</h3>
              <ul className="space-y-1">
                {(activeGroup as Extract<GroupData, { narrative: unknown }>).narrative.key_moments.map((m, i) => (
                  <li key={i} className="text-sm text-ink-light">• {m}</li>
                ))}
              </ul>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <MindReadingToggle />
    </div>
  )
}
