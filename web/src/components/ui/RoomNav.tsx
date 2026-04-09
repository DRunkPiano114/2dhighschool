import { useMemo, useEffect, useRef } from 'react'
import { useWorldStore } from '../../stores/useWorldStore'
import { LOCATION_ICONS } from '../../lib/constants'
import type { SceneIndexEntry } from '../../lib/types'

interface TimeSlot {
  key: string // "08:45|课间"
  time: string
  name: string
  scenes: SceneIndexEntry[]
}

function groupScenesByTimeSlot(scenes: SceneIndexEntry[]): TimeSlot[] {
  const slots: TimeSlot[] = []
  for (const scene of scenes) {
    const last = slots[slots.length - 1]
    if (last && last.time === scene.time && last.name === scene.name) {
      last.scenes.push(scene)
    } else {
      slots.push({
        key: `${scene.time}|${scene.name}`,
        time: scene.time,
        name: scene.name,
        scenes: [scene],
      })
    }
  }
  return slots
}

export function RoomNav() {
  const scenes = useWorldStore(s => s.scenes)
  const currentSceneIndex = useWorldStore(s => s.currentSceneIndex)
  const setScene = useWorldStore(s => s.setCurrentSceneIndex)
  const activeRef = useRef<HTMLButtonElement>(null)

  const slots = useMemo(() => groupScenesByTimeSlot(scenes), [scenes])

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [currentSceneIndex])

  if (scenes.length <= 1) return null

  return (
    <div className="absolute left-3 top-1/2 -translate-y-1/2 z-30 pointer-events-auto">
      <div className="flex flex-col gap-0.5 bg-black/40 backdrop-blur-sm rounded-xl p-1.5 max-h-[70vh] overflow-y-auto">
        {slots.map(slot => {
          const slotActive = slot.scenes.some(s => s.scene_index === currentSceneIndex)

          if (slot.scenes.length === 1) {
            const scene = slot.scenes[0]
            const icon = LOCATION_ICONS[scene.location] ?? '📍'
            const isActive = scene.scene_index === currentSceneIndex
            return (
              <button
                key={slot.key}
                ref={isActive ? activeRef : undefined}
                onClick={() => setScene(scene.scene_index)}
                className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs transition-colors text-left ${
                  isActive
                    ? 'bg-white/20 text-white'
                    : 'text-white/50 hover:text-white/70 hover:bg-white/10'
                }`}
                title={`${scene.time} ${scene.name} — ${scene.location}`}
              >
                <span className="text-[10px] text-white/40 w-8 shrink-0">{scene.time}</span>
                <span className="text-sm">{icon}</span>
                <span className="text-[10px] leading-none">{scene.name}</span>
              </button>
            )
          }

          return (
            <div key={slot.key}>
              <div
                className={`flex items-center gap-1.5 px-2 py-1 text-xs ${
                  slotActive ? 'text-amber-400/80' : 'text-white/30'
                }`}
              >
                <span className="text-[10px] w-8 shrink-0">{slot.time}</span>
                <span className="text-[10px] leading-none">{slot.name}</span>
              </div>
              {slot.scenes.map(scene => {
                const icon = LOCATION_ICONS[scene.location] ?? '📍'
                const isActive = scene.scene_index === currentSceneIndex
                return (
                  <button
                    key={scene.scene_index}
                    ref={isActive ? activeRef : undefined}
                    onClick={() => setScene(scene.scene_index)}
                    className={`flex items-center gap-1.5 pl-5 pr-2 py-1 rounded-lg text-xs transition-colors w-full text-left ${
                      isActive
                        ? 'bg-white/20 text-white'
                        : 'text-white/50 hover:text-white/70 hover:bg-white/10'
                    }`}
                    title={scene.location}
                  >
                    <span className="text-sm">{icon}</span>
                    <span className="text-[10px] leading-none">{scene.location}</span>
                  </button>
                )
              })}
            </div>
          )
        })}
      </div>
    </div>
  )
}
