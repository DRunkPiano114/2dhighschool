import type { AgentDayJson } from '../../lib/types'
import './share-card.css'

/**
 * Agent archive share card — pure renderer. Consumes the serialized
 * build_agent_spec() output from /data/agents/{id}/days/{day:03d}.json.
 * Mirrors the structure the Python PIL card used but stays HTML/CSS so we
 * can capture it with html-to-image.
 */
export function AgentShareCard({ data }: { data: AgentDayJson }) {
  const subtitle = data.is_teacher
    ? `${data.motif_emoji} ${data.motif_tag} · 语文`
    : `${data.motif_emoji} ${data.motif_tag} · 学生`

  return (
    <div className="share-card agent-share-card">
      <div
        className="agent-share-color-strip"
        style={{ backgroundColor: data.main_color }}
      />

      <div className="agent-share-inner">
        <header className="agent-share-header">
          <div className="share-seal share-seal--date">
            第{String(data.day).padStart(3, '0')}天
          </div>
          <div className="agent-share-header-body">
            <h1 className="agent-share-name">{data.name_cn}</h1>
            <p className="agent-share-motif">{subtitle.trim()}</p>
          </div>
        </header>

        <hr className="share-divider agent-share-divider" />

        <div className="agent-share-body">
          <img
            className="agent-share-portrait"
            src={`/data/portraits/${data.agent_id}.png`}
            alt={data.name_cn}
          />
          <div className="agent-share-state">
            <div className="agent-share-state-row">
              <span className="agent-share-state-label">情绪</span>
              <span className="agent-share-state-value">
                {data.emotion_label || '—'}
              </span>
            </div>
            <div className="agent-share-state-row">
              <span className="agent-share-state-label">精力</span>
              <span className="agent-share-state-value">
                {data.energy_label || '—'}
              </span>
            </div>
            <div className="agent-share-state-row">
              <span className="agent-share-state-label">压力</span>
              <span className="agent-share-state-value">
                {data.pressure_label || '—'}
              </span>
            </div>
            {data.top_concern && !data.is_teacher && (
              <div className="agent-share-state-row">
                <span className="agent-share-state-label agent-share-state-concern-label">
                  {data.top_concern.positive ? '期待' : '挂怀'}
                </span>
                <span className="agent-share-state-value agent-share-state-value--concern">
                  {data.top_concern.intensity_label} · {data.top_concern.text}
                </span>
              </div>
            )}
          </div>
        </div>

        {data.featured_quote && (
          <>
            <p className="agent-share-quote-label">今日金句</p>
            <div className="agent-share-quote-bubble">
              （{data.name_cn} 心想）{data.featured_quote}
            </div>
            {data.featured_scene && (
              <p className="agent-share-quote-meta">— {data.featured_scene}</p>
            )}
          </>
        )}

        {data.relationships.length > 0 && !data.is_teacher && (
          <>
            <p className="agent-share-rel-title">
              此刻关系 TOP {data.relationships.length}
            </p>
            {data.relationships.map((r, i) => (
              <div key={i} className="agent-share-rel-row">
                <span className="agent-share-rel-name">{r.target_name}</span>
                <span className="agent-share-rel-meta">
                  {r.label_text} · 好感 {r.favorability >= 0 ? '+' : ''}
                  {r.favorability}  信任 {r.trust >= 0 ? '+' : ''}
                  {r.trust}
                </span>
              </div>
            ))}
          </>
        )}
      </div>

      <footer className="share-brand-footer">
        <hr className="share-divider" />
        <h2 className="share-brand-footer-title">SimCampus · AI 校园模拟器</h2>
        <p className="share-brand-footer-tag">每天都在上演</p>
        <div className="share-seal share-seal--brand">班</div>
      </footer>
    </div>
  )
}
