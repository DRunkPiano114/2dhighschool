import { useWorldStore } from '../../stores/useWorldStore'
import type { SceneGroup } from '../../lib/types'
import { EnvironmentalBanner } from './EnvironmentalBanner'
import { GroupPills } from './GroupPills'
import { FocalCard } from './FocalCard'
import { SoloCard } from './SoloCard'
import { ObserverRow } from './ObserverRow'
import { TickNav } from './TickNav'
import { pickFocal, partitionObservers } from './focal'

export function NarrativePanel() {
  const sceneFile = useWorldStore(s => s.currentSceneFile)
  const scenes = useWorldStore(s => s.scenes)
  const sceneIdx = useWorldStore(s => s.currentSceneIndex)
  const groupIdx = useWorldStore(s => s.activeGroupIndex)
  const currentTick = useWorldStore(s => s.currentTick)

  const wrapperClass = [
    'relative z-30 flex-shrink-0',
    'bg-[#141422] border-t border-white/5',
    'flex flex-col overflow-hidden',
    'h-[60vh] md:h-[45vh]',
  ].join(' ')

  // Loading skeleton — scene index set but file not yet loaded
  if (!sceneFile) {
    return (
      <div className={wrapperClass}>
        <SkeletonPanel />
      </div>
    )
  }

  const group = sceneFile.groups[groupIdx]
  const sceneInfo = scenes[sceneIdx] ?? sceneFile.scene

  // Solo group
  if (group?.is_solo) {
    const agentId = group.participants[0]
    const name = sceneFile.participant_names[agentId] ?? agentId
    return (
      <div className={wrapperClass}>
        <EnvironmentalBanner />
        <GroupPills />
        <div className="flex-1 min-h-0 overflow-y-auto">
          <SoloCard
            agentId={agentId}
            agentName={name}
            soloReflection={group.solo_reflection}
          />
        </div>
      </div>
    )
  }

  const ticks = group ? (group as SceneGroup).ticks : []

  // Trivial / empty group
  if (!group || ticks.length === 0) {
    return (
      <div className={wrapperClass}>
        <EnvironmentalBanner />
        <GroupPills />
        <div className="flex-1 flex items-center justify-center text-white/40 text-sm italic font-serif px-6 text-center">
          （平静的时刻 — {sceneInfo?.name ?? ''}）
        </div>
      </div>
    )
  }

  const tick = ticks[Math.min(currentTick, ticks.length - 1)]
  if (!tick) {
    return (
      <div className={wrapperClass}>
        <EnvironmentalBanner />
        <GroupPills />
        <div className="flex-1 flex items-center justify-center text-white/40 text-sm italic">
          （场景过渡中…）
        </div>
        <TickNav />
      </div>
    )
  }

  const focal = pickFocal(tick, group as SceneGroup)
  const observers = partitionObservers(tick, focal.agentId)
  const speakerName = sceneFile.participant_names[focal.agentId] ?? focal.agentId
  const targetName = focal.target
    ? sceneFile.participant_names[focal.target] ?? focal.target
    : undefined
  const focalMind = tick.minds[focal.agentId]

  return (
    <div className={wrapperClass}>
      <EnvironmentalBanner />
      <GroupPills />
      <div className="flex-1 min-h-0 overflow-y-auto flex flex-col">
        <FocalCard
          focal={focal}
          speakerName={speakerName}
          targetName={targetName ?? undefined}
          mind={focalMind}
          tickIdx={currentTick}
        />
        <ObserverRow
          observers={observers}
          participantNames={sceneFile.participant_names}
        />
      </div>
      <TickNav />
    </div>
  )
}

function SkeletonPanel() {
  return (
    <div className="flex-1 animate-pulse flex flex-col gap-3 p-4">
      <div className="h-4 bg-white/5 rounded w-3/4" />
      <div className="h-20 bg-white/5 rounded" />
      <div className="h-3 bg-white/5 rounded w-2/3" />
      <div className="h-3 bg-white/5 rounded w-1/2" />
      <div className="h-3 bg-white/5 rounded w-3/5" />
    </div>
  )
}
