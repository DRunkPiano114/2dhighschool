import { useEffect, useState } from 'react'
import type { GameEvent, Meta } from '../../lib/types'
import { loadEvents, loadMeta } from '../../lib/data'
import { EventCard } from './EventCard'

export function PropagationView() {
  const [events, setEvents] = useState<GameEvent[]>([])
  const [meta, setMeta] = useState<Meta | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([loadEvents(), loadMeta()]).then(([e, m]) => {
      setEvents(e)
      setMeta(m)
      setLoading(false)
    })
  }, [])

  if (loading) {
    return (
      <div className="text-center py-20">
        <div className="inline-block w-6 h-6 border-2 border-amber border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const agentNames = meta
    ? Object.fromEntries(Object.entries(meta.agents).map(([id, a]) => [id, a.name]))
    : {}

  if (events.length === 0) {
    return (
      <div>
        <h1 className="text-xl font-medium mb-4">八卦传播</h1>
        <div className="text-center py-16 bg-white rounded-xl border border-gray-100">
          <p className="text-ink-light">还没有发生什么八卦...</p>
          <p className="text-sm text-ink-light/60 mt-1">运行模拟后，事件会出现在这里</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-xl font-medium mb-1">八卦传播</h1>
      <p className="text-sm text-ink-light mb-4">
        共 {events.length} 个事件 · 点击展开查看传播详情
      </p>
      <div className="space-y-3">
        {events.map((event) => (
          <EventCard
            key={event.id}
            event={event}
            agentNames={agentNames}
            expanded={expandedId === event.id}
            onToggle={() => setExpandedId(expandedId === event.id ? null : event.id)}
          />
        ))}
      </div>
    </div>
  )
}
