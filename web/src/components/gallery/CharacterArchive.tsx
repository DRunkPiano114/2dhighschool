import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorldStore } from '../../stores/useWorldStore'
import { ShareButtons } from '../narrative/ShareButtons'

interface RelationshipPreview {
  target_name: string
  favorability: number
  trust: number
  label_text: string
}

interface MemoryPreview {
  date: string
  text: string
  importance: number
}

interface ConcernPreview {
  text: string
  intensity_label: string
  positive: boolean
}

interface AgentJson {
  agent_id: string
  name_cn: string
  day: number
  is_teacher: boolean
  motif_emoji: string
  motif_tag: string
  main_color: string
  emotion_label: string
  energy_label: string
  pressure_label: string
  featured_quote: string | null
  featured_scene: string | null
  relationships: RelationshipPreview[]
  memories: MemoryPreview[]
  top_concern: ConcernPreview | null
  self_narrative: string
  caption_payload: { caption: string; hashtags: string[]; filename: string }
}

export function CharacterArchive({
  agentId,
  dayId,
  days,
}: {
  agentId: string
  dayId: string
  days: string[] | null
}) {
  const [data, setData] = useState<AgentJson | null>(null)
  const [loading, setLoading] = useState(true)
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)

  const dayNum = (() => {
    const m = dayId.match(/day_0*(\d+)/)
    return m ? parseInt(m[1], 10) : null
  })()

  const openRolePlay = useWorldStore(s => s.openRolePlayChat)

  useEffect(() => {
    if (dayNum === null) return
    let alive = true
    setLoading(true)
    fetch(`/api/card/agent/${agentId}/${dayNum}.json`)
      .then(async r => {
        if (!alive) return
        if (!r.ok) {
          setApiOnline(false)
          setLoading(false)
          return
        }
        setApiOnline(true)
        setData(await r.json())
        setLoading(false)
      })
      .catch(() => {
        if (alive) {
          setApiOnline(false)
          setLoading(false)
        }
      })
    return () => { alive = false }
  }, [agentId, dayNum])

  if (dayNum === null) {
    return <div className="archive-root archive-error">无效的日期：{dayId}</div>
  }

  return (
    <div className="archive-root">
      <header className="archive-nav">
        <Link to={`/day/${dayId}`} className="archive-back">← 日报</Link>
        <ArchiveDayNav agentId={agentId} dayId={dayId} days={days} />
      </header>

      {loading && <div className="archive-loading">加载中…</div>}

      {!loading && apiOnline === false && (
        <div className="archive-offline">
          <p>档案卡需要 API 才能生成。</p>
          <p className="daily-offline-cmd">请先执行 <code>uv run api</code>。</p>
        </div>
      )}

      {!loading && data && (
        <>
          <div
            className={`archive-hero${data.is_teacher ? ' archive-hero-teacher' : ''}`}
            style={{ ['--agent-color' as string]: data.main_color }}
          >
            <img
              src={`/data/portraits/${data.agent_id}.png`}
              alt={data.name_cn}
              className="archive-portrait"
            />
            <div className="archive-identity">
              <div className="archive-day">第{String(data.day).padStart(3, '0')}天</div>
              <h1 className="archive-name">{data.name_cn}</h1>
              <div className="archive-motif">
                {data.motif_emoji} {data.motif_tag} · {data.is_teacher ? '班主任 · 语文' : '学生'}
              </div>
            </div>
          </div>

          <div className="archive-state-row">
            <StatePill label="情绪" value={data.emotion_label} />
            <StatePill label="精力" value={data.energy_label} />
            <StatePill label="压力" value={data.pressure_label} />
          </div>

          <div className="archive-actions">
            <ShareButtons
              cardEndpoint={`/api/card/agent/${data.agent_id}/${data.day}`}
              cardLabel="档案卡"
            />
            <button
              type="button"
              className="archive-roleplay-btn"
              onClick={() => {
                // Open role-play chat with this character as the target,
                // leaving user-agent selection open (user picks in the modal).
                openRolePlay(data.agent_id, [data.agent_id])
              }}
              disabled={apiOnline !== true}
              title={apiOnline !== true ? 'API 未启动' : `以此身份与 ${data.name_cn} 聊聊`}
            >
              与 {data.name_cn} 聊聊 →
            </button>
          </div>

          {data.featured_quote && (
            <section className="archive-section">
              <h2 className="archive-section-title">今日金句</h2>
              <blockquote className="archive-quote">
                <span>{data.featured_quote}</span>
                {data.featured_scene && (
                  <footer>— {data.featured_scene}</footer>
                )}
              </blockquote>
            </section>
          )}

          {data.top_concern && !data.is_teacher && (
            <section className="archive-section">
              <h2 className="archive-section-title">
                {data.top_concern.positive ? '今日期待' : '今日挂怀'}
              </h2>
              <div className="archive-concern">
                <span className="archive-concern-label">{data.top_concern.intensity_label}</span>
                <span className="archive-concern-text">{data.top_concern.text}</span>
              </div>
            </section>
          )}

          {data.relationships.length > 0 && (
            <section className="archive-section">
              <h2 className="archive-section-title">此刻关系 TOP {data.relationships.length}</h2>
              <ul className="archive-rel-list">
                {data.relationships.map((r, i) => (
                  <li key={i} className="archive-rel-row">
                    <span className="archive-rel-name">{r.target_name}</span>
                    <span className="archive-rel-label">{r.label_text}</span>
                    <span className="archive-rel-stats">
                      好感 {r.favorability >= 0 ? '+' : ''}{r.favorability} · 信任 {r.trust >= 0 ? '+' : ''}{r.trust}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {data.memories.length > 0 && (
            <section className="archive-section">
              <h2 className="archive-section-title">近期记忆</h2>
              <ul className="archive-mem-list">
                {data.memories.map((m, i) => (
                  <li key={i} className="archive-mem-row">
                    <div className="archive-mem-date">{m.date}</div>
                    <div className="archive-mem-text">{m.text}</div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}

function StatePill({ label, value }: { label: string; value: string }) {
  return (
    <div className="state-pill">
      <span className="state-pill-label">{label}</span>
      <span className="state-pill-value">{value || '—'}</span>
    </div>
  )
}

function ArchiveDayNav({
  agentId,
  dayId,
  days,
}: {
  agentId: string
  dayId: string
  days: string[] | null
}) {
  if (!days) return null
  const idx = days.indexOf(dayId)
  const prev = idx > 0 ? days[idx - 1] : null
  const next = idx >= 0 && idx < days.length - 1 ? days[idx + 1] : null
  return (
    <div className="archive-day-nav">
      {prev ? (
        <Link to={`/characters/${agentId}?day=${prev}`}>◀ 昨日</Link>
      ) : (
        <span className="daily-nav-btn-disabled">◀ 昨日</span>
      )}
      <span className="archive-day-label">{dayId.replace('day_', '第')}天</span>
      {next ? (
        <Link to={`/characters/${agentId}?day=${next}`}>明日 ▶</Link>
      ) : (
        <span className="daily-nav-btn-disabled">明日 ▶</span>
      )}
    </div>
  )
}
