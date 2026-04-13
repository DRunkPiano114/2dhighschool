import { useWorldStore } from '../../stores/useWorldStore'
import type { SceneGroup } from '../../lib/types'

/**
 * Derived from the current group + currentTick:
 * - The most-recent non-empty environmental_event at or before currentTick.
 * - Any public.exits since that event (persist until the next event
 *   overrides, or the group ends).
 * No internal state — everything comes from the tick stream, so switching
 * scene/group implicitly resets the banner.
 */
export function EnvironmentalBanner() {
  const sceneFile = useWorldStore(s => s.currentSceneFile)
  const groupIdx = useWorldStore(s => s.activeGroupIndex)
  const currentTick = useWorldStore(s => s.currentTick)
  const participantNames = sceneFile?.participant_names ?? {}

  const group = sceneFile?.groups[groupIdx]
  const ticks = group && !group.is_solo ? (group as SceneGroup).ticks : []

  let lastEnv: string | null = null
  let lastEnvTickIdx = -1
  const upperBound = Math.min(currentTick, ticks.length - 1)
  for (let i = 0; i <= upperBound; i++) {
    const ev = ticks[i]?.public.environmental_event
    if (ev) {
      lastEnv = ev
      lastEnvTickIdx = i
    }
  }

  const activeExitNames: string[] = []
  for (let i = lastEnvTickIdx + 1; i <= upperBound; i++) {
    const exits = ticks[i]?.public.exits ?? []
    for (const agentId of exits) {
      const name = participantNames[agentId] ?? agentId
      if (!activeExitNames.includes(name)) activeExitNames.push(name)
    }
  }

  if (!lastEnv && activeExitNames.length === 0) return null

  return (
    <div className="px-4 py-2 text-xs space-y-1 text-white/60 border-b border-white/5">
      {lastEnv && (
        <div className="flex items-center gap-2">
          <span className="text-white/40">🌐</span>
          <span>{lastEnv}</span>
        </div>
      )}
      {activeExitNames.map(name => (
        <div key={name} className="text-white/40 italic text-center">
          —— {name} 离开教室 ——
        </div>
      ))}
    </div>
  )
}
