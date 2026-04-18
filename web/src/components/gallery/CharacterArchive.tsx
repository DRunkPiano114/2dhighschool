import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ShareButtons } from '../narrative/ShareButtons'
import { AgentShareCard } from '../share/AgentShareCard'
import { useShareCapture } from '../share/useShareCapture'
import { useChatApiOnline } from '../../lib/useChatApiOnline'
import { RolePlaySetup } from '../ui/RolePlaySetup'
import type { AgentDayJson } from '../../lib/types'

export function CharacterArchive({
  agentId,
  dayId,
  days,
}: {
  agentId: string
  dayId: string
  days: string[] | null
}) {
  const [data, setData] = useState<AgentDayJson | null>(null)
  const [loading, setLoading] = useState(true)
  const [showSetup, setShowSetup] = useState(false)
  const chatOnline = useChatApiOnline()
  const { nodeRef, capture } = useShareCapture()

  const dayNum = (() => {
    const m = dayId.match(/day_0*(\d+)/)
    return m ? parseInt(m[1], 10) : null
  })()

  useEffect(() => {
    if (dayNum === null) return
    let alive = true
    setLoading(true)
    setData(null)
    fetch(`/data/agents/${agentId}/days/${String(dayNum).padStart(3, '0')}.json`)
      .then(async r => {
        if (!alive) return
        if (!r.ok) {
          setLoading(false)
          return
        }
        setData(await r.json())
        setLoading(false)
      })
      .catch(() => {
        if (alive) setLoading(false)
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

      {!loading && !data && (
        <div className="archive-offline">
          <p>本日档案缺失。</p>
          <p className="daily-offline-cmd">请先执行 <code>uv run python scripts/export_frontend_data.py</code>。</p>
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
              cardLabel="档案卡"
              capture={capture}
              meta={data.caption_payload}
            />
            <button
              type="button"
              className="archive-roleplay-btn"
              onClick={() => setShowSetup(true)}
              disabled={chatOnline !== true}
              title={chatOnline !== true ? 'API 未启动' : `与 ${data.name_cn} 聊聊`}
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
      {data && (
        <div className="share-offscreen" aria-hidden>
          <div ref={nodeRef} className="share-offscreen-node">
            <AgentShareCard data={data} />
          </div>
        </div>
      )}
      {showSetup && data && (
        <RolePlaySetup
          initialTargetId={data.agent_id}
          onClose={() => setShowSetup(false)}
        />
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
