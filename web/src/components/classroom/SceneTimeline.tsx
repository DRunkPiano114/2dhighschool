import { Link } from 'react-router-dom'
import type { ScheduleEntry, SceneIndexEntry } from '../../lib/types'
import { LOCATION_ICONS } from '../../lib/constants'

interface SceneTimelineProps {
  schedule: ScheduleEntry[]
  scenes: SceneIndexEntry[]
  dayId: string
}

export function SceneTimeline({ schedule, scenes, dayId }: SceneTimelineProps) {
  // Match schedule entries to available scene files
  const scenesByTime = new Map(scenes.map((s) => [s.time, s]))

  return (
    <div className="mt-8">
      <h2 className="text-base font-medium text-ink-light mb-3">今日场景</h2>
      <div className="flex gap-2 overflow-x-auto pb-2">
        {schedule.map((entry) => {
          const scene = scenesByTime.get(entry.time)
          const hasData = !!scene
          const icon = LOCATION_ICONS[entry.location] ?? '📍'
          // Strip .json extension and build the scene file param
          const sceneFile = scene?.file.replace('.json', '')

          if (!hasData) {
            return (
              <div
                key={entry.time}
                className="flex-shrink-0 px-3 py-2 rounded-lg bg-gray-50 border border-gray-100 opacity-50"
              >
                <div className="text-xs text-ink-light">{entry.time}</div>
                <div className="text-sm mt-0.5">{icon} {entry.name}</div>
              </div>
            )
          }

          return (
            <Link
              key={entry.time}
              to={`/day/${dayId}/scene/${sceneFile}`}
              className="flex-shrink-0 px-3 py-2 rounded-lg bg-white border border-gray-100 hover:border-teal/50 hover:bg-teal/5 transition-colors shadow-sm"
            >
              <div className="text-xs text-ink-light">{entry.time}</div>
              <div className="text-sm mt-0.5 font-medium">{icon} {entry.name}</div>
              <div className="text-xs text-ink-light mt-0.5">{scene!.groups.length} 组</div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
