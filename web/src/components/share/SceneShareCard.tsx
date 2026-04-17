import type { SceneLayoutJson } from '../../lib/types'
import './share-card.css'

/**
 * Scene share card — pure renderer. Python's scene_to_layout_spec owns every
 * selection decision (featured tick, portrait ordering, bubble choice,
 * featured_quote). This component consumes that layout dict and lays it out
 * at 1080×1440, ready for html-to-image capture.
 */
export function SceneShareCard({ layout }: { layout: SceneLayoutJson }) {
  const n = layout.portraits.length
  const portraitClass =
    n <= 2
      ? 'scene-share-portrait-img scene-share-portrait-img--large'
      : n >= 4
      ? 'scene-share-portrait-img scene-share-portrait-img--small'
      : 'scene-share-portrait-img'
  const portraitsClass =
    n >= 4 ? 'scene-share-portraits scene-share-portraits--four' : 'scene-share-portraits'

  return (
    <div className="share-card scene-share-card">
      <header className="scene-share-header">
        <div className="share-seal share-seal--date">
          第{String(layout.day).padStart(3, '0')}天
        </div>
        <div className="scene-share-header-body">
          <h1 className="scene-share-title">
            {layout.time} · {layout.scene_name}
          </h1>
          <p className="scene-share-subtitle">{layout.location}</p>
        </div>
      </header>

      <hr className="share-divider scene-share-divider" />

      {n > 0 && (
        <div className={portraitsClass}>
          {layout.portraits.map(p => (
            <div key={p.agent_id} className="scene-share-portrait">
              <img
                className={portraitClass}
                src={`/data/portraits/${p.agent_id}.png`}
                alt={p.name_cn}
              />
              <p className="scene-share-portrait-name">{p.name_cn}</p>
              {(p.motif_emoji || p.motif_tag) && (
                <p className="scene-share-portrait-motif">
                  {p.motif_emoji} {p.motif_tag}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {layout.bubbles.length > 0 && (
        <div className="scene-share-bubbles">
          {layout.bubbles.map((b, i) => (
            <div
              key={i}
              className={`scene-share-bubble scene-share-bubble--${b.kind}`}
            >
              <span className="scene-share-bubble-speaker">
                {b.kind === 'thought'
                  ? `（${b.display_name} 心想）`
                  : `${b.display_name}：`}
              </span>
              <span className="scene-share-bubble-text">{b.text}</span>
            </div>
          ))}
        </div>
      )}

      <footer className="share-brand-footer">
        <hr className="share-divider" />
        <h2 className="share-brand-footer-title">SimCampus · AI 校园模拟器</h2>
        <p className="share-brand-footer-tag">每天都在上演</p>
        <div className="share-seal share-seal--brand">班</div>
      </footer>
    </div>
  )
}
