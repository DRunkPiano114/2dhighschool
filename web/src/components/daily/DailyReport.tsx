import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { loadMeta } from '../../lib/data'
import { EMOTION_LABELS, LOCATION_ICONS } from '../../lib/constants'
import { ShareButtons } from '../narrative/ShareButtons'
import type { Emotion } from '../../lib/types'

interface Beat {
  scene_time: string
  scene_name: string
  scene_location: string
  scene_file: string
  group_index: number
  tick_index: number
  speaker_id: string
  speaker_name: string
  speech: string | null
  thought_id: string | null
  thought_name: string | null
  thought: string | null
  urgency: number
}

interface MoodEntry {
  agent_id: string
  agent_name: string
  dominant_emotion: Emotion
  emotion_counts: Record<string, number>
  main_color: string
  motif_emoji: string
}

interface CP {
  a_id: string
  a_name: string
  b_id: string
  b_name: string
  favorability_delta: number
  trust_delta: number
  understanding_delta: number
}

interface GoldenQuote {
  agent_id: string
  agent_name: string
  text: string
  scene_time: string
  scene_name: string
}

interface SceneThumb {
  time: string
  name: string
  location: string
  file: string
  participants: string[]
}

interface AgentRef {
  agent_id: string
  agent_name: string
}

interface TopEventCardData {
  text: string
  category: string
  scene_file: string
  scene_time: string
  scene_name: string
  witnesses: AgentRef[]
  non_witnesses: AgentRef[]
  pull_quote: string | null
  pull_quote_agent_id: string | null
  pull_quote_agent_name: string | null
  group_index: number
  tick_index: number
}

interface ContrastMismatchPayload {
  a_id: string
  a_name: string
  a_thought: string
  a_emotion: string
  b_id: string
  b_name: string
  b_thought: string
  b_emotion: string
  fav_a_to_b: number
  fav_b_to_a: number
}

interface ContrastFailedIntentPayload {
  agent_id: string
  agent_name: string
  goal: string
  status: 'frustrated' | 'missed_opportunity' | string
  brief_reason: string
  urgency_proxy: number
}

interface ContrastSilentJudgmentPayload {
  target_id: string
  target_name: string
  accusers: { id: string; name: string; fav_delta: number }[]
}

interface ContrastCardData {
  kind: 'mismatch' | 'failed_intent' | 'silent_judgment'
  payload: ContrastMismatchPayload | ContrastFailedIntentPayload | ContrastSilentJudgmentPayload
  scene_time: string | null
  scene_name: string | null
  scene_file: string | null
  group_index: number
  tick_index: number
}

interface ConcernCardData {
  agent_id: string
  agent_name: string
  text: string
  topic: string
  intensity: number
  reinforcement_count: number
  days_active: number
  first_day: number
  reinforced_today: boolean
}

interface DailySummaryJson {
  day: number
  headline: Beat | null
  secondaries: Beat[]
  mood_map: MoodEntry[]
  cp: CP | null
  golden_quote: GoldenQuote | null
  scene_thumbs: SceneThumb[]
  top_event?: TopEventCardData | null
  contrast?: ContrastCardData | null
  concern_spotlight?: ConcernCardData | null
  caption_payload: {
    caption: string
    hashtags: string[]
    filename: string
  }
}

// Entry route `/` — decide the latest day, then redirect.
export function DailyReportHome() {
  const [dayId, setDayId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadMeta()
      .then(m => {
        const latest = m.days[m.days.length - 1]
        setDayId(latest || 'day_001')
      })
      .catch(e => setError(String(e)))
  }, [])

  if (error) return <div className="daily-root daily-error">数据加载失败：{error}</div>
  if (!dayId) return <div className="daily-root daily-loading">加载中…</div>
  return <Navigate to={`/day/${dayId}`} replace />
}

export function DailyReport() {
  const { dayId } = useParams<{ dayId: string }>()
  const day = useMemo(() => {
    if (!dayId) return null
    const m = dayId.match(/day_0*(\d+)/)
    return m ? parseInt(m[1], 10) : null
  }, [dayId])

  const [summary, setSummary] = useState<DailySummaryJson | null>(null)
  const [loading, setLoading] = useState(true)
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)
  const [days, setDays] = useState<string[] | null>(null)
  const captureRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadMeta().then(m => setDays(m.days)).catch(() => setDays(null))
  }, [])

  useEffect(() => {
    if (day === null) return
    let alive = true
    setLoading(true)
    setSummary(null)
    fetch(`/api/card/daily/${day}.json`)
      .then(async r => {
        if (!alive) return
        if (!r.ok) {
          setApiOnline(false)
          setLoading(false)
          return
        }
        setApiOnline(true)
        setSummary(await r.json())
        setLoading(false)
      })
      .catch(() => {
        if (alive) {
          setApiOnline(false)
          setLoading(false)
        }
      })
    return () => { alive = false }
  }, [day])

  if (!dayId || day === null) {
    return <div className="daily-root daily-error">无效的日期：{dayId}</div>
  }

  return (
    <div className="daily-root" ref={captureRef}>
      <DailyTopBar dayId={dayId} day={day} days={days} />

      {loading && <div className="daily-loading">加载今日日报中…</div>}

      {!loading && apiOnline === false && (
        <div className="daily-offline">
          <p>API 未启动，无法生成今日日报。</p>
          <p className="daily-offline-cmd">请先执行 <code>uv run api</code>。</p>
          <Link to={`/day/${dayId}/scene/first`} className="daily-offline-fallback">
            进入场景视图（不需要 API）→
          </Link>
        </div>
      )}

      {!loading && summary && (
        <>
          <div className="daily-actions" data-exclude-from-capture>
            <ShareButtons
              cardEndpoint={`/api/card/daily/${summary.day}`}
              cardLabel="今日日报"
              showCopy={false}
              captureTarget={captureRef}
            />
          </div>
          <div className="daily-body">
            <div className="daily-col daily-col-left">
              {summary.top_event
                ? <DailyTopEvent data={summary.top_event} dayId={dayId} />
                : summary.headline && <DailyHeadline headline={summary.headline} dayId={dayId} />}
              {summary.contrast
                ? <DailyContrast data={summary.contrast} dayId={dayId} />
                : summary.golden_quote && <DailyQuote quote={summary.golden_quote} />}
              {summary.concern_spotlight
                ? <DailyConcern data={summary.concern_spotlight} />
                : <DailySecondaries beats={summary.secondaries} dayId={dayId} />}
            </div>
            <div className="daily-col daily-col-right">
              <MoodMap entries={summary.mood_map} dayId={dayId} />
              {summary.cp && <CPTracker cp={summary.cp} />}
              <SceneStrip thumbs={summary.scene_thumbs} dayId={dayId} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// --- helpers ---------------------------------------------------------------

/** Build a scene URL that preserves group/tick when a Beat is the source. */
function sceneHref(dayId: string, file: string, beat?: Pick<Beat, 'group_index' | 'tick_index'>): string {
  const base = `/day/${dayId}/scene/${file}`
  if (!beat) return base
  return `${base}?g=${beat.group_index}&t=${beat.tick_index}`
}

// --- Sub-components --------------------------------------------------------

function DailyTopBar({
  dayId,
  day,
  days,
}: {
  dayId: string
  day: number
  days: string[] | null
}) {
  const sceneLink = (
    <Link
      to={`/day/${dayId}/scene/first`}
      className="seal-btn seal-btn--gold seal-btn--lg"
      aria-label="现场 — 进入场景视图"
      title="现场 — 进入场景视图"
    >
      <span className="seal-btn-text">现场</span>
    </Link>
  )
  const hero = (
    <div className="daily-nav-center">
      <span className="daily-hero-seal">第{String(day).padStart(3, '0')}天</span>
      <h1 className="daily-hero-title">班级日报</h1>
      <span className="daily-hero-subtitle">一天里的教室、宿舍、操场与心事</span>
    </div>
  )
  if (!days) {
    return (
      <nav className="daily-nav">
        <div className="daily-nav-left" data-exclude-from-capture />
        {hero}
        <div className="daily-nav-right" data-exclude-from-capture>{sceneLink}</div>
      </nav>
    )
  }
  const idx = days.indexOf(dayId)
  const prev = idx > 0 ? days[idx - 1] : null
  const next = idx >= 0 && idx < days.length - 1 ? days[idx + 1] : null
  return (
    <nav className="daily-nav">
      <div className="daily-nav-left" data-exclude-from-capture>
        {prev ? (
          <Link to={`/day/${prev}`} className="daily-nav-btn">◀ 昨日</Link>
        ) : (
          <span className="daily-nav-btn daily-nav-btn-disabled">◀ 昨日</span>
        )}
        {next ? (
          <Link to={`/day/${next}`} className="daily-nav-btn">明日 ▶</Link>
        ) : (
          <span className="daily-nav-btn daily-nav-btn-disabled">明日 ▶</span>
        )}
      </div>
      {hero}
      <div className="daily-nav-right" data-exclude-from-capture>{sceneLink}</div>
    </nav>
  )
}

function DailyHeadline({ headline, dayId }: { headline: Beat; dayId: string }) {
  return (
    <section className="daily-section daily-headline">
      <h2 className="daily-section-title">今日头条</h2>
      <div className="daily-headline-meta">
        {headline.scene_time} · {headline.scene_name} · {LOCATION_ICONS[headline.scene_location] ?? ''} {headline.scene_location}
      </div>
      {headline.speech && (
        <div className="daily-speech">
          <span className="daily-speech-speaker">{headline.speaker_name}</span>
          <span className="daily-speech-text">"{headline.speech}"</span>
        </div>
      )}
      {headline.thought && (
        <div className="daily-thought">
          <span className="daily-thought-label">（{headline.thought_name} 心想）</span>
          <span className="daily-thought-text">{headline.thought}</span>
        </div>
      )}
      <div className="daily-headline-link">
        <Link to={sceneHref(dayId, headline.scene_file, headline)}>
          进入现场 →
        </Link>
      </div>
    </section>
  )
}

function DailyQuote({ quote }: { quote: GoldenQuote }) {
  return (
    <section className="daily-section daily-quote-section">
      <h2 className="daily-section-title">今日金句</h2>
      <blockquote className="daily-quote">
        <span className="daily-quote-text">{quote.text}</span>
        <footer className="daily-quote-footer">
          — {quote.agent_name} · {quote.scene_time} {quote.scene_name}
        </footer>
      </blockquote>
    </section>
  )
}

function DailySecondaries({ beats, dayId }: { beats: Beat[]; dayId: string }) {
  if (beats.length === 0) return null
  return (
    <section className="daily-section daily-secondaries">
      <h2 className="daily-section-title">次条</h2>
      <ul className="daily-secondary-list">
        {beats.map((b, i) => (
          <li key={i} className="daily-secondary-item">
            <Link to={sceneHref(dayId, b.scene_file, b)} className="daily-secondary-link">
              <span className="daily-secondary-meta">
                {b.scene_time} · {b.scene_name}@{b.scene_location}
              </span>
              <span className="daily-secondary-body">
                {b.speech
                  ? `${b.speaker_name}：${b.speech}`
                  : b.thought
                    ? `（${b.thought_name} 心想）${b.thought}`
                    : '（静默）'}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

function MoodMap({ entries, dayId }: { entries: MoodEntry[]; dayId: string }) {
  if (entries.length === 0) return null
  return (
    <section className="daily-section daily-mood-map">
      <h2 className="daily-section-title">人物志</h2>
      <ul className="mood-grid">
        {entries.map(e => (
          <li key={e.agent_id} className="mood-cell">
            <Link
              to={`/characters/${e.agent_id}?day=${dayId}`}
              className="mood-cell-link"
              aria-label={`${e.agent_name} — 查看当日人物志`}
              title={`${e.agent_name} — 查看当日人物志`}
            >
              <img
                className="mood-sprite"
                src={`/data/map_sprites/${e.agent_id}.png`}
                alt=""
                aria-hidden
              />
              <div className="mood-name">{e.agent_name}</div>
              <div className="mood-emotion">
                {e.motif_emoji} {EMOTION_LABELS[e.dominant_emotion] ?? e.dominant_emotion}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

function CPTracker({ cp }: { cp: CP }) {
  return (
    <section className="daily-section daily-cp">
      <h2 className="daily-section-title">今日 CP</h2>
      <div className="cp-row">
        <div className="cp-name">{cp.a_name}</div>
        <div className="cp-heart" aria-hidden>♥</div>
        <div className="cp-name">{cp.b_name}</div>
      </div>
      <div className="cp-deltas">
        <span>好感 +{cp.favorability_delta}</span>
        <span>信任 +{cp.trust_delta}</span>
        <span>理解 +{cp.understanding_delta}</span>
      </div>
    </section>
  )
}

function SceneStrip({ thumbs, dayId }: { thumbs: SceneThumb[]; dayId: string }) {
  if (thumbs.length === 0) return null
  return (
    <section className="daily-section daily-scene-strip">
      <h2 className="daily-section-title">今日场景</h2>
      <ul className="scene-strip-list">
        {thumbs.map((t, i) => (
          <li key={i} className="scene-strip-item">
            <Link to={`/day/${dayId}/scene/${t.file}`} className="scene-strip-link">
              <div className="scene-strip-icon">
                {LOCATION_ICONS[t.location] ?? '📍'}
              </div>
              <div className="scene-strip-meta">
                <div className="scene-strip-time">{t.time}</div>
                <div className="scene-strip-name">{t.name}</div>
                <div className="scene-strip-loc">{t.location}</div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

const TOPIC_COLOR: Record<string, string> = {
  '恋爱': '#d64c7a',
  '人际矛盾': '#b54b35',
  '家庭压力': '#946635',
  '自我认同': '#6a559b',
  '学业焦虑': '#3e7db3',
  '未来规划': '#2f8a73',
  '健康': '#4d8f4a',
  '兴趣爱好': '#a67e28',
  '期待的事': '#a67e28',
  '其他': '#777',
}

function categoryTone(category: string): string {
  const cat = category || ''
  if (/八卦|流言|恋爱|暗恋|绯闻/.test(cat)) return 'gossip'
  if (/冲突|威胁|违纪|纪律|警告|批评/.test(cat)) return 'conflict'
  if (/社交|邀请|邀约|约定|社交活动/.test(cat)) return 'social'
  if (/学习|学业|学术/.test(cat)) return 'academic'
  return 'default'
}

function DailyTopEvent({ data, dayId }: { data: TopEventCardData; dayId: string }) {
  const tone = categoryTone(data.category)
  return (
    <section className={`daily-section daily-topevent daily-topevent--${tone}`}>
      <h2 className="daily-section-title">今日头条</h2>
      <div className="daily-topevent-head">
        <span className="daily-topevent-category">{data.category || '事件'}</span>
        <span className="daily-topevent-meta">
          {data.scene_time} · {data.scene_name}
        </span>
      </div>
      <p className="daily-topevent-text">{data.text}</p>
      {data.pull_quote && (
        <blockquote className="daily-topevent-quote">
          <span className="daily-topevent-quote-text">"{data.pull_quote}"</span>
          {data.pull_quote_agent_name && (
            <footer className="daily-topevent-quote-footer">
              — {data.pull_quote_agent_name}
            </footer>
          )}
        </blockquote>
      )}
      <div className="daily-topevent-witnesses">
        <div className="daily-topevent-row">
          <span className="daily-topevent-row-label">知情</span>
          <ul className="daily-topevent-faces">
            {data.witnesses.map(w => (
              <li key={w.agent_id} className="daily-topevent-face daily-topevent-face--lit" title={w.agent_name}>
                <img src={`/data/map_sprites/${w.agent_id}.png`} alt="" aria-hidden />
                <span className="daily-topevent-face-name">{w.agent_name}</span>
              </li>
            ))}
          </ul>
        </div>
        {data.non_witnesses.length > 0 && (
          <div className="daily-topevent-row">
            <span className="daily-topevent-row-label">还不知道</span>
            <ul className="daily-topevent-faces">
              {data.non_witnesses.map(w => (
                <li key={w.agent_id} className="daily-topevent-face daily-topevent-face--dim" title={w.agent_name}>
                  <img src={`/data/map_sprites/${w.agent_id}.png`} alt="" aria-hidden />
                  <span className="daily-topevent-face-name">{w.agent_name}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {data.scene_file && (
        <div className="daily-headline-link">
          <Link to={sceneHref(dayId, data.scene_file, data)}>进入现场 →</Link>
        </div>
      )}
    </section>
  )
}

function DailyContrast({ data, dayId }: { data: ContrastCardData; dayId: string }) {
  const sceneMeta = data.scene_time && data.scene_name
    ? `${data.scene_time} · ${data.scene_name}`
    : null
  return (
    <section className={`daily-section daily-contrast daily-contrast--${data.kind}`}>
      <h2 className="daily-section-title">今日对照</h2>
      {data.kind === 'mismatch' && (
        <DailyContrastMismatch payload={data.payload as ContrastMismatchPayload} />
      )}
      {data.kind === 'failed_intent' && (
        <DailyContrastFailed payload={data.payload as ContrastFailedIntentPayload} />
      )}
      {data.kind === 'silent_judgment' && (
        <DailyContrastSilent payload={data.payload as ContrastSilentJudgmentPayload} />
      )}
      {(sceneMeta || data.scene_file) && (
        <div className="daily-contrast-footer">
          {sceneMeta && <span className="daily-contrast-meta">{sceneMeta}</span>}
          {data.scene_file && (
            <Link to={sceneHref(dayId, data.scene_file, data)} className="daily-contrast-link">
              进入现场 →
            </Link>
          )}
        </div>
      )}
    </section>
  )
}

function DailyContrastMismatch({ payload }: { payload: ContrastMismatchPayload }) {
  return (
    <>
      <div className="daily-contrast-tag">错位</div>
      <div className="daily-contrast-mismatch">
        <MismatchSide
          agentId={payload.a_id}
          name={payload.a_name}
          emotion={payload.a_emotion}
          fav={payload.fav_a_to_b}
          towardsName={payload.b_name}
          thought={payload.a_thought}
        />
        <div className="daily-contrast-mismatch-divider" aria-hidden>⇅</div>
        <MismatchSide
          agentId={payload.b_id}
          name={payload.b_name}
          emotion={payload.b_emotion}
          fav={payload.fav_b_to_a}
          towardsName={payload.a_name}
          thought={payload.b_thought}
        />
      </div>
    </>
  )
}

function MismatchSide({
  agentId, name, emotion, fav, towardsName, thought,
}: {
  agentId: string; name: string; emotion: string; fav: number; towardsName: string; thought: string
}) {
  const favLabel = fav > 0 ? `+${fav}` : `${fav}`
  return (
    <div className="daily-contrast-side">
      <div className="daily-contrast-side-head">
        <img className="daily-contrast-sprite" src={`/data/map_sprites/${agentId}.png`} alt="" aria-hidden />
        <div className="daily-contrast-side-name">{name}</div>
        <div className="daily-contrast-side-emotion">
          {EMOTION_LABELS[emotion as Emotion] ?? emotion}
        </div>
      </div>
      <div className="daily-contrast-side-fav">
        对 {towardsName} <span className={`daily-contrast-favbadge daily-contrast-favbadge--${fav >= 0 ? 'pos' : 'neg'}`}>好感 {favLabel}</span>
      </div>
      <blockquote className="daily-contrast-side-thought">{thought}</blockquote>
    </div>
  )
}

function DailyContrastFailed({ payload }: { payload: ContrastFailedIntentPayload }) {
  const statusLabel = payload.status === 'frustrated' ? '受挫' : '错过时机'
  return (
    <>
      <div className="daily-contrast-tag">今日翻车</div>
      <div className="daily-contrast-failed">
        <div className="daily-contrast-failed-row">
          <img className="daily-contrast-sprite" src={`/data/map_sprites/${payload.agent_id}.png`} alt="" aria-hidden />
          <div className="daily-contrast-failed-name">{payload.agent_name}</div>
        </div>
        <div className="daily-contrast-failed-arrow">
          <span className="daily-contrast-failed-goal">想：{payload.goal}</span>
          <span className="daily-contrast-failed-sep" aria-hidden>→</span>
          <span className={`daily-contrast-failed-status daily-contrast-failed-status--${payload.status}`}>
            却：{statusLabel}
          </span>
        </div>
        <p className="daily-contrast-failed-reason">{payload.brief_reason}</p>
      </div>
    </>
  )
}

function DailyContrastSilent({ payload }: { payload: ContrastSilentJudgmentPayload }) {
  return (
    <>
      <div className="daily-contrast-tag">暗戳戳</div>
      <div className="daily-contrast-silent">
        <div className="daily-contrast-silent-target">
          <img className="daily-contrast-sprite daily-contrast-sprite--big" src={`/data/map_sprites/${payload.target_id}.png`} alt="" aria-hidden />
          <div className="daily-contrast-silent-name">{payload.target_name}</div>
          <div className="daily-contrast-silent-subtitle">背后被扣分</div>
        </div>
        <ul className="daily-contrast-silent-accusers">
          {payload.accusers.map(a => (
            <li key={a.id} className="daily-contrast-silent-accuser">
              <img className="daily-contrast-sprite" src={`/data/map_sprites/${a.id}.png`} alt="" aria-hidden />
              <span className="daily-contrast-silent-accuser-name">{a.name}</span>
              <span className="daily-contrast-silent-fav">{a.fav_delta}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}

function DailyConcern({ data }: { data: ConcernCardData }) {
  const topicColor = TOPIC_COLOR[data.topic] ?? TOPIC_COLOR['其他']
  const intensityCells = Array.from({ length: 10 }, (_, i) => i < data.intensity)
  const showCrossDay = data.reinforcement_count > 0 || data.days_active > 1
  return (
    <section className="daily-section daily-concern">
      <h2 className="daily-section-title">心事聚光</h2>
      <div className="daily-concern-head">
        <img className="daily-concern-sprite" src={`/data/map_sprites/${data.agent_id}.png`} alt="" aria-hidden />
        <div className="daily-concern-head-main">
          <div className="daily-concern-name-row">
            <span className="daily-concern-name">{data.agent_name}</span>
            <span
              className="daily-concern-topic"
              style={{ backgroundColor: topicColor }}
            >
              {data.topic}
            </span>
          </div>
          {showCrossDay && (
            <div className="daily-concern-badges">
              <span className="daily-concern-badge daily-concern-badge--days">
                第 {data.days_active} 天
              </span>
              {data.reinforcement_count > 0 && (
                <span className="daily-concern-badge daily-concern-badge--rc">
                  重新浮现 {data.reinforcement_count} 次
                </span>
              )}
              {data.reinforced_today && data.reinforcement_count > 0 && (
                <span className="daily-concern-badge daily-concern-badge--today">
                  今日又想起
                </span>
              )}
            </div>
          )}
        </div>
      </div>
      <p className="daily-concern-text">{data.text}</p>
      <div className="daily-concern-intensity">
        <span className="daily-concern-intensity-label">强度</span>
        <span className="daily-concern-intensity-bar">
          {intensityCells.map((on, i) => (
            <span
              key={i}
              className={`daily-concern-intensity-cell ${on ? 'is-on' : ''}`}
              aria-hidden
            />
          ))}
        </span>
        <span className="daily-concern-intensity-value">{data.intensity}/10</span>
      </div>
    </section>
  )
}
