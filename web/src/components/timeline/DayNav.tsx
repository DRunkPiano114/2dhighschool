interface DayNavProps {
  days: string[]
  currentDay: string
  onSelect: (day: string) => void
}

export function DayNav({ days, currentDay, onSelect }: DayNavProps) {
  if (days.length <= 1) return null

  return (
    <div className="flex gap-1 mb-4 overflow-x-auto pb-1">
      {days.map((day) => {
        const num = parseInt(day.replace('day_', ''), 10)
        return (
          <button
            key={day}
            onClick={() => onSelect(day)}
            className={`flex-shrink-0 px-3 py-1 rounded-md text-sm transition-colors ${
              day === currentDay
                ? 'bg-amber/15 text-amber font-medium'
                : 'text-ink-light hover:bg-gray-100'
            }`}
          >
            第{num}天
          </button>
        )
      })}
    </div>
  )
}
