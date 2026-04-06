import { useWorldStore } from '../../stores/useWorldStore'
import { scoreTick } from '../../lib/drama'
import type { PlaybackSpeed, SceneGroup } from '../../lib/types'
import { LOCATION_ICONS } from '../../lib/constants'

export function BottomBar() {
  const scene = useWorldStore(s => s.currentSceneFile)
  const scenes = useWorldStore(s => s.scenes)
  const sceneIdx = useWorldStore(s => s.currentSceneIndex)
  const groupIdx = useWorldStore(s => s.activeGroupIndex)
  const tick = useWorldStore(s => s.currentTick)
  const setTick = useWorldStore(s => s.setCurrentTick)
  const setScene = useWorldStore(s => s.setCurrentSceneIndex)
  const setGroup = useWorldStore(s => s.setActiveGroupIndex)
  const isPlaying = useWorldStore(s => s.isPlaying)
  const setPlaying = useWorldStore(s => s.setIsPlaying)
  const speed = useWorldStore(s => s.playbackSpeed)
  const setSpeed = useWorldStore(s => s.setPlaybackSpeed)

  if (!scene) return null

  const group = scene.groups[groupIdx]
  const ticks = group && !group.is_solo ? (group as SceneGroup).ticks : []
  const tickScores = ticks.map(scoreTick)
  const maxScore = Math.max(1, ...tickScores)
  const sceneInfo = scenes[sceneIdx]

  return (
    <div className="absolute bottom-0 left-0 right-0 z-30 pointer-events-none">
      <div className="mx-4 mb-3 pointer-events-auto bg-black/50 backdrop-blur-sm rounded-xl px-4 py-3">
        {/* Scene info + group tabs */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-white/40">{sceneInfo?.time}</span>
            <span className="text-white/80 font-medium">
              {LOCATION_ICONS[sceneInfo?.location ?? ''] ?? ''}{' '}
              {sceneInfo?.name}@{sceneInfo?.location}
            </span>
          </div>

          {/* Group tabs */}
          <div className="flex items-center gap-1">
            {scene.groups.map((g, i) => {
              const names = g.participants
                .map(p => scene.participant_names[p]?.slice(0, 1) ?? '?')
                .join('')
              return (
                <button
                  key={i}
                  onClick={() => setGroup(i)}
                  className={`px-2 py-0.5 rounded text-xs transition-colors ${
                    i === groupIdx
                      ? 'bg-amber-500/80 text-white'
                      : 'bg-white/10 text-white/50 hover:text-white/70'
                  }`}
                  title={g.participants.map(p => scene.participant_names[p]).join(', ')}
                >
                  {g.is_solo ? '🧘' : `G${i + 1}`} {names}
                </button>
              )
            })}
          </div>

          {/* Scene stepper */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => sceneIdx > 0 && setScene(sceneIdx - 1)}
              className="text-white/40 hover:text-white/70 text-xs px-1"
              disabled={sceneIdx === 0}
            >
              ◀ 上一场
            </button>
            <span className="text-white/30 text-xs">
              {sceneIdx + 1}/{scenes.length}
            </span>
            <button
              onClick={() => sceneIdx < scenes.length - 1 && setScene(sceneIdx + 1)}
              className="text-white/40 hover:text-white/70 text-xs px-1"
              disabled={sceneIdx >= scenes.length - 1}
            >
              下一场 ▶
            </button>
          </div>
        </div>

        {/* Tick scrubber */}
        {ticks.length > 0 && (
          <div className="flex items-center gap-3">
            {/* Play/pause */}
            <button
              onClick={() => setPlaying(!isPlaying)}
              className="text-white/80 hover:text-white text-lg w-6"
            >
              {isPlaying ? '⏸' : '▶'}
            </button>

            {/* Speed */}
            <div className="flex gap-0.5">
              {([1, 2, 4] as PlaybackSpeed[]).map(s => (
                <button
                  key={s}
                  onClick={() => setSpeed(s)}
                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                    speed === s
                      ? 'bg-white/20 text-white'
                      : 'text-white/40 hover:text-white/60'
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>

            {/* Scrubber track */}
            <div className="flex-1 flex items-end gap-px h-6">
              {ticks.map((_, i) => {
                const intensity = tickScores[i] / maxScore
                const isCurrent = i === tick
                return (
                  <button
                    key={i}
                    onClick={() => setTick(i)}
                    className="flex-1 relative group"
                    style={{ minWidth: 4 }}
                  >
                    <div
                      className="w-full rounded-sm transition-colors"
                      style={{
                        height: `${Math.max(4, intensity * 20)}px`,
                        background: isCurrent
                          ? '#f59e0b'
                          : `rgba(255,255,255,${0.15 + intensity * 0.35})`,
                      }}
                    />
                    {isCurrent && (
                      <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-amber-400 rounded-full" />
                    )}
                  </button>
                )
              })}
            </div>

            {/* Tick counter */}
            <span className="text-white/40 text-xs font-mono min-w-[3rem] text-right">
              {tick + 1}/{ticks.length}
            </span>
          </div>
        )}

        {/* Solo indicator */}
        {group?.is_solo && (
          <div className="text-white/50 text-xs text-center py-1">
            🧘 独处中 — {scene.participant_names[group.participants[0]]}
          </div>
        )}
      </div>
    </div>
  )
}
