interface RelationshipCardProps {
  fromName: string
  toName: string
  favorability: number
  trust: number
  understanding: number
  label: string
  recentInteractions: string[]
}

export function RelationshipCard({
  fromName,
  toName,
  favorability,
  trust,
  understanding,
  label,
  recentInteractions,
}: RelationshipCardProps) {
  return (
    <div className="p-4 bg-white rounded-xl shadow-md border border-gray-100 w-72">
      <div className="flex items-center justify-between mb-3">
        <span className="font-medium text-sm">{fromName} → {toName}</span>
        <span className="text-xs text-ink-light px-1.5 py-0.5 bg-gray-50 rounded">{label}</span>
      </div>
      <div className="space-y-2">
        {[
          { label: '好感', value: favorability, color: favorability >= 0 ? '#7AB893' : '#D94848' },
          { label: '信任', value: trust, color: trust >= 0 ? '#5a8f7b' : '#E8A838' },
          { label: '了解', value: understanding, color: '#d4a853' },
        ].map(({ label: l, value, color }) => (
          <div key={l} className="flex items-center gap-2">
            <span className="text-xs text-ink-light w-8">{l}</span>
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(Math.abs(value), 100) / 2}%`,
                  backgroundColor: color,
                }}
              />
            </div>
            <span className="text-xs w-8 text-right text-ink-light">{value}</span>
          </div>
        ))}
      </div>
      {recentInteractions.length > 0 && (
        <div className="mt-3 pt-2 border-t border-gray-50">
          <p className="text-xs text-ink-light mb-1">最近互动</p>
          {recentInteractions.slice(0, 3).map((text, i) => (
            <p key={i} className="text-xs text-ink/70 truncate">• {text}</p>
          ))}
        </div>
      )}
    </div>
  )
}
