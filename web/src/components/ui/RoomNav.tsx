import { useWorldStore } from '../../stores/useWorldStore'
import { LOCATION_ICONS } from '../../lib/constants'
import type { RoomId } from '../../lib/types'

/** Rooms that have scenes in the current day. */
function useActiveRooms(): RoomId[] {
  const scenes = useWorldStore(s => s.scenes)
  const rooms = new Set<RoomId>()
  for (const s of scenes) rooms.add(s.location as RoomId)
  return [...rooms]
}

export function RoomNav() {
  const activeRooms = useActiveRooms()
  const currentRoom = useWorldStore(s => s.currentRoom)
  const scenes = useWorldStore(s => s.scenes)
  const setScene = useWorldStore(s => s.setCurrentSceneIndex)

  if (activeRooms.length <= 1) return null

  function handleClick(room: RoomId) {
    // Jump to first scene in this room
    const idx = scenes.findIndex(s => s.location === room)
    if (idx >= 0) setScene(idx)
  }

  return (
    <div className="absolute left-3 top-1/2 -translate-y-1/2 z-30 pointer-events-auto">
      <div className="flex flex-col gap-1.5 bg-black/40 backdrop-blur-sm rounded-xl p-1.5">
        {activeRooms.map(room => {
          const icon = LOCATION_ICONS[room] ?? '📍'
          const isActive = room === currentRoom
          return (
            <button
              key={room}
              onClick={() => handleClick(room)}
              className={`flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-lg text-xs transition-colors ${
                isActive
                  ? 'bg-white/20 text-white'
                  : 'text-white/50 hover:text-white/70 hover:bg-white/10'
              }`}
              title={room}
            >
              <span className="text-base">{icon}</span>
              <span className="text-[10px] leading-none">{room}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
