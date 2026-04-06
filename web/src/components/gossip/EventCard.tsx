import type { GameEvent } from '../../lib/types'

const CATEGORY_COLORS: Record<string, string> = {
  social: 'bg-purple-100 text-purple-700',
  academic: 'bg-blue-100 text-blue-700',
  conflict: 'bg-red-100 text-red-700',
  romantic: 'bg-pink-100 text-pink-700',
  rumor: 'bg-orange-100 text-orange-700',
}

interface EventCardProps {
  event: GameEvent
  agentNames: Record<string, string>
  expanded: boolean
  onToggle: () => void
}

export function EventCard({ event, agentNames, expanded, onToggle }: EventCardProps) {
  const catClass = CATEGORY_COLORS[event.category] ?? 'bg-gray-100 text-gray-700'

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full p-4 text-left hover:bg-gray-50/50 transition-colors"
      >
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">{event.text}</p>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className={`px-1.5 py-0.5 rounded text-xs ${catClass}`}>
                {event.category || '未分类'}
              </span>
              <span className="text-xs text-ink-light">
                第{event.source_day}天 · {event.source_scene}
              </span>
            </div>
          </div>
          {/* Spread probability bar */}
          <div className="flex-shrink-0 w-16">
            <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-amber"
                style={{ width: `${event.spread_probability * 100}%` }}
              />
            </div>
            <p className="text-[10px] text-ink-light text-center mt-0.5">
              {Math.round(event.spread_probability * 100)}% 传播率
            </p>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-50">
          <div className="pt-3 space-y-3">
            {/* Witnesses */}
            <div>
              <p className="text-xs text-ink-light mb-1">目击者</p>
              <div className="flex flex-wrap gap-1">
                {event.witnesses.map((w) => (
                  <span key={w} className="px-2 py-0.5 rounded-full text-xs bg-teal/10 text-teal">
                    {agentNames[w] ?? w}
                  </span>
                ))}
                {event.witnesses.length === 0 && (
                  <span className="text-xs text-ink-light">无</span>
                )}
              </div>
            </div>

            {/* Known by */}
            <div>
              <p className="text-xs text-ink-light mb-1">已知者</p>
              <div className="flex flex-wrap gap-1">
                {event.known_by.map((k) => (
                  <span key={k} className="px-2 py-0.5 rounded-full text-xs bg-amber/10 text-amber">
                    {agentNames[k] ?? k}
                  </span>
                ))}
                {event.known_by.length === 0 && (
                  <span className="text-xs text-ink-light">暂无人知道</span>
                )}
              </div>
            </div>

            {/* Propagation visualization */}
            {event.witnesses.length > 0 && event.known_by.length > event.witnesses.length && (
              <div className="pt-2">
                <p className="text-xs text-ink-light mb-2">传播路径</p>
                <div className="flex items-center gap-2 flex-wrap">
                  {event.witnesses.map((w) => (
                    <span key={w} className="text-xs font-medium text-teal">
                      {agentNames[w] ?? w}
                    </span>
                  ))}
                  <span className="text-ink-light">→</span>
                  {event.known_by
                    .filter((k) => !event.witnesses.includes(k))
                    .map((k) => (
                      <span key={k} className="text-xs font-medium text-amber">
                        {agentNames[k] ?? k}
                      </span>
                    ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
