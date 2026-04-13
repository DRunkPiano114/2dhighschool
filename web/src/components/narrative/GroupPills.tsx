import { useWorldStore } from '../../stores/useWorldStore'

export function GroupPills() {
  const sceneFile = useWorldStore(s => s.currentSceneFile)
  const groupIdx = useWorldStore(s => s.activeGroupIndex)
  const setGroup = useWorldStore(s => s.setActiveGroupIndex)

  if (!sceneFile || sceneFile.groups.length <= 1) return null

  return (
    <div className="px-4 py-2 flex items-center gap-1.5 flex-wrap">
      {sceneFile.groups.map((g, i) => {
        const names = g.participants
          .map(p => sceneFile.participant_names[p] ?? p)
        const label = g.is_solo
          ? `🧘 ${names[0]}`
          : `G${i + 1} ${names.map(n => n.slice(0, 1)).join('')}`
        const active = i === groupIdx
        return (
          <button
            key={i}
            onClick={() => setGroup(i)}
            title={names.join(', ')}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
              active
                ? 'bg-amber-500/80 text-white'
                : 'bg-white/5 text-white/55 hover:bg-white/10 hover:text-white/80'
            }`}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
