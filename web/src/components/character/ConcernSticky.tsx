import type { ActiveConcern } from '../../lib/types'

const ROTATIONS = [-3, 1, -2, 2.5, -1, 3, -0.5, 1.5]
const COLORS = [
  'bg-yellow-100 border-yellow-300',
  'bg-amber-50 border-amber-200',
  'bg-orange-50 border-orange-200',
  'bg-lime-50 border-lime-200',
]

interface ConcernStickyProps {
  concern: ActiveConcern
  index: number
}

export function ConcernSticky({ concern, index }: ConcernStickyProps) {
  const rotation = ROTATIONS[index % ROTATIONS.length]
  const colorClass = COLORS[index % COLORS.length]
  const borderWidth = Math.min(concern.intensity, 10) > 6 ? 'border-2' : 'border'

  return (
    <div
      className={`sticky-note p-3 rounded-sm shadow-md ${colorClass} ${borderWidth}`}
      style={{ transform: `rotate(${rotation}deg)` }}
    >
      <p className="text-sm font-hand leading-snug">{concern.text}</p>
      {concern.related_people.length > 0 && (
        <p className="text-xs text-ink-light mt-1.5">
          相关：{concern.related_people.join('、')}
        </p>
      )}
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-xs text-ink-light">
          {concern.positive ? '✨' : '😟'} {concern.emotion}
        </span>
        <div className="flex gap-0.5">
          {Array.from({ length: Math.min(concern.intensity, 10) }, (_, i) => (
            <span key={i} className="w-1 h-2 rounded-sm bg-amber/60" />
          ))}
        </div>
      </div>
    </div>
  )
}
