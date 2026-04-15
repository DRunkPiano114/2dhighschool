import { useEffect, useState, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { loadMeta } from '../../lib/data'
import { CharacterArchive } from './CharacterArchive'

interface AgentPreview {
  agent_id: string
  name: string
  role: string
  is_teacher: boolean
}

/**
 * 2×5 gallery of all agents for a given day. Each tile links to the archive
 * detail page. The portrait PNG comes directly from `/data/portraits/`, so
 * the gallery renders even when the API is offline — only the drill-in card
 * needs the server.
 */
export function CharacterGallery() {
  const { dayId: dayIdParam } = useParams<{ dayId: string }>()
  const [days, setDays] = useState<string[] | null>(null)
  const [agents, setAgents] = useState<AgentPreview[] | null>(null)

  useEffect(() => {
    loadMeta().then(m => {
      setDays(m.days)
      const list: AgentPreview[] = Object.entries(m.agents).map(([id, a]) => ({
        agent_id: id,
        name: a.name,
        role: a.role,
        is_teacher: a.role === 'homeroom_teacher',
      }))
      // Students first, teacher last.
      list.sort((a, b) => {
        if (a.is_teacher !== b.is_teacher) return a.is_teacher ? 1 : -1
        return a.name.localeCompare(b.name)
      })
      setAgents(list)
    })
  }, [])

  const dayId = dayIdParam ?? (days ? days[days.length - 1] : null)
  const dayNum = useMemo(() => {
    if (!dayId) return null
    const m = dayId.match(/day_0*(\d+)/)
    return m ? parseInt(m[1], 10) : null
  }, [dayId])

  return (
    <div className="gallery-root">
      <header className="gallery-header">
        <Link to={dayId ? `/day/${dayId}` : '/'} className="gallery-back">← 返回日报</Link>
        <h1 className="gallery-title">人物志</h1>
        <div className="gallery-spacer" />
      </header>

      {dayId && <GalleryDayNav dayId={dayId} days={days} />}

      {!agents || !dayNum ? (
        <div className="gallery-loading">加载中…</div>
      ) : (
        <ul className="gallery-grid">
          {agents.map(a => (
            <li key={a.agent_id}>
              <Link
                to={`/characters/${a.agent_id}?day=${encodeURIComponent(dayId ?? 'day_001')}`}
                className={`gallery-tile${a.is_teacher ? ' gallery-tile-teacher' : ''}`}
              >
                <img
                  src={`/data/portraits/${a.agent_id}.png`}
                  alt={a.name}
                  className="gallery-portrait"
                  loading="lazy"
                />
                <div className="gallery-name">{a.name}</div>
                {a.is_teacher && <div className="gallery-role">班主任</div>}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function GalleryDayNav({ dayId, days }: { dayId: string; days: string[] | null }) {
  if (!days) return null
  const idx = days.indexOf(dayId)
  const prev = idx > 0 ? days[idx - 1] : null
  const next = idx >= 0 && idx < days.length - 1 ? days[idx + 1] : null
  return (
    <nav className="gallery-day-nav">
      {prev ? <Link to={`/characters/day/${prev}`}>◀ 昨日</Link> : <span className="daily-nav-btn-disabled">◀ 昨日</span>}
      <span className="gallery-day-label">{dayId.replace('day_', '第')}天</span>
      {next ? <Link to={`/characters/day/${next}`}>明日 ▶</Link> : <span className="daily-nav-btn-disabled">明日 ▶</span>}
    </nav>
  )
}

/**
 * Entry point for `/characters/:agentId`. Reads day from ?day= query param
 * (defaults to latest if omitted), fetches the archive, renders the modal.
 */
export function CharacterArchivePage() {
  const { agentId } = useParams<{ agentId: string }>()
  const [search] = useSearchParams()
  const [days, setDays] = useState<string[] | null>(null)

  useEffect(() => {
    loadMeta().then(m => setDays(m.days)).catch(() => setDays(null))
  }, [])

  const dayId = search.get('day') ?? (days ? days[days.length - 1] : null)
  if (!agentId || !dayId) {
    return <div className="gallery-loading">加载中…</div>
  }
  return <CharacterArchive agentId={agentId} dayId={dayId} days={days} />
}
