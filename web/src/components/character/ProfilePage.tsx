import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import type { Agent } from '../../lib/types'
import { loadAgent } from '../../lib/data'
import { EMOTION_COLORS } from '../../lib/constants'
import { EmotionBadge } from './EmotionBadge'
import { ConcernSticky } from './ConcernSticky'
import { AcademicsBadge } from './AcademicsBadge'

const PRESSURE_LABELS: Record<string, { label: string; color: string; width: string }> = {
  '低': { label: '低', color: 'bg-emerald-400', width: 'w-1/4' },
  '中': { label: '中', color: 'bg-amber-400', width: 'w-1/2' },
  '高': { label: '高', color: 'bg-red-400', width: 'w-3/4' },
}

export function ProfilePage() {
  const { agentId } = useParams<{ agentId: string }>()
  const [agent, setAgent] = useState<Agent | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!agentId) return
    setAgent(null)
    setError(false)
    loadAgent(agentId).then(setAgent).catch(() => setError(true))
  }, [agentId])

  if (error) {
    return (
      <div className="text-center py-20">
        <p className="text-ink-light mb-4">无法加载角色信息</p>
        <Link to="/" className="text-teal hover:underline">返回教室</Link>
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="text-center py-20">
        <div className="inline-block w-6 h-6 border-2 border-amber border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const emotionColor = EMOTION_COLORS[agent.state.emotion] ?? '#B8B8B8'
  const pressure = PRESSURE_LABELS[agent.family_background.pressure_level] ?? PRESSURE_LABELS['中']
  const relationships = Object.values(agent.relationships)
  const sortedRels = [...relationships].sort((a, b) => b.favorability - a.favorability)

  return (
    <div className="max-w-4xl mx-auto">
      <Link to="/" className="text-sm text-ink-light hover:text-teal transition-colors">
        ← 返回教室
      </Link>

      <div className="mt-4 ruled-paper bg-white rounded-xl shadow-md p-6 md:p-8">
        <div className="grid md:grid-cols-2 gap-8">
          {/* Left column */}
          <div className="space-y-5">
            {/* Name & basic info */}
            <div>
              <div className="flex items-center gap-3 mb-2">
                <div
                  className="w-12 h-12 rounded-full flex items-center justify-center text-white text-xl font-medium"
                  style={{ backgroundColor: emotionColor }}
                >
                  {agent.name[0]}
                </div>
                <div>
                  <h1 className="text-2xl font-hand">{agent.name}</h1>
                  <EmotionBadge emotion={agent.state.emotion} size="md" />
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-3">
                <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100">{agent.gender === 'male' ? '男' : '女'}</span>
                {agent.seat_number && <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100">座位 {agent.seat_number}</span>}
                {agent.dorm_id && <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100">{agent.dorm_id}</span>}
                {agent.position && <span className="px-2 py-0.5 rounded-full text-xs bg-amber/20 text-amber">{agent.position}</span>}
              </div>
            </div>

            {/* Personality */}
            <div>
              <h2 className="text-base font-medium text-ink-light mb-2">性格标签</h2>
              <div className="flex flex-wrap gap-1.5">
                {agent.personality.map((tag) => (
                  <span key={tag} className="px-2 py-1 rounded-md text-sm font-hand bg-teal/10 text-teal">
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            {/* Academics */}
            <div>
              <h2 className="text-base font-medium text-ink-light mb-2">学业</h2>
              <AcademicsBadge academics={agent.academics} />
            </div>

            {/* Family */}
            <div>
              <h2 className="text-base font-medium text-ink-light mb-2">家庭</h2>
              <div className="p-3 bg-gray-50 rounded-lg text-sm space-y-2">
                <p className="text-ink/80">{agent.family_background.expectation}</p>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-ink-light">压力</span>
                  <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${pressure.color} ${pressure.width} transition-all`} />
                  </div>
                  <span className="text-xs font-medium">{pressure.label}</span>
                </div>
              </div>
            </div>

            {/* Inner conflicts */}
            <div>
              <h2 className="text-base font-medium text-ink-light mb-2">内心矛盾</h2>
              <ul className="space-y-1">
                {agent.inner_conflicts.map((c, i) => (
                  <li key={i} className="text-sm text-ink/80 font-hand">• {c}</li>
                ))}
              </ul>
            </div>
          </div>

          {/* Right column */}
          <div className="space-y-5">
            {/* Active concerns as sticky notes */}
            {agent.state.active_concerns.length > 0 && (
              <div>
                <h2 className="text-base font-medium text-ink-light mb-3">当前关注</h2>
                <div className="grid grid-cols-2 gap-3">
                  {agent.state.active_concerns.map((concern, i) => (
                    <ConcernSticky key={i} concern={concern} index={i} />
                  ))}
                </div>
              </div>
            )}

            {/* Self-narrative */}
            {agent.self_narrative && (
              <div>
                <h2 className="text-base font-medium text-ink-light mb-2">自我叙事</h2>
                <div className="p-4 bg-amber/5 rounded-lg border border-amber/10">
                  <p className="text-sm font-hand leading-relaxed text-ink/80 whitespace-pre-line">
                    {agent.self_narrative}
                  </p>
                </div>
              </div>
            )}

            {/* Relationships mini-map */}
            {sortedRels.length > 0 && (
              <div>
                <h2 className="text-base font-medium text-ink-light mb-3">人际关系</h2>
                <div className="space-y-2">
                  {sortedRels.map((rel) => (
                    <Link
                      key={rel.target_id}
                      to={`/character/${rel.target_id}`}
                      className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 transition-colors"
                    >
                      <div className="w-7 h-7 rounded-full bg-teal/20 flex items-center justify-center text-xs font-medium text-teal">
                        {rel.target_name[0]}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{rel.target_name}</span>
                          <span className="text-xs text-ink-light">{rel.label}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all"
                              style={{
                                width: `${Math.abs(rel.favorability) / 2}%`,
                                backgroundColor: rel.favorability >= 0 ? '#7AB893' : '#D94848',
                              }}
                            />
                          </div>
                          <span className="text-xs text-ink-light w-8 text-right">{rel.favorability > 0 ? '+' : ''}{rel.favorability}</span>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
