import { useEffect, useState, useMemo } from 'react'
import type { Meta, DayTrajectory } from '../../lib/types'
import { loadMeta, loadTrajectory } from '../../lib/data'
import { EMOTION_COLORS, EMOTION_LABELS, EMOTION_SENTIMENT } from '../../lib/constants'

interface DataPoint {
  scene: string
  emotion: string
  sentiment: number
  dayIndex: number
  sceneIndex: number
}

export function EmotionTimeline() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [trajectories, setTrajectories] = useState<DayTrajectory[]>([])
  const [selectedAgents, setSelectedAgents] = useState<string[]>([])
  const [hoveredPoint, setHoveredPoint] = useState<{ agentId: string; point: DataPoint; x: number; y: number } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadMeta().then(async (m) => {
      setMeta(m)
      const trajs = await Promise.all(
        m.days.map((day) => loadTrajectory(day).catch(() => null))
      )
      setTrajectories(trajs.filter((t): t is DayTrajectory => t !== null))
      // Pre-select first 3 students
      const studentIds = Object.entries(m.agents)
        .filter(([, a]) => a.role === 'student')
        .map(([id]) => id)
        .slice(0, 3)
      setSelectedAgents(studentIds)
      setLoading(false)
    })
  }, [])

  // Build per-agent data series
  const agentSeries = useMemo(() => {
    const series: Record<string, DataPoint[]> = {}
    trajectories.forEach((traj, dayIdx) => {
      for (const [agentId, slots] of Object.entries(traj.agents)) {
        if (!series[agentId]) series[agentId] = []
        slots.forEach((slot, sceneIdx) => {
          const emotion = slot.emotion || 'neutral'
          series[agentId].push({
            scene: `${slot.time} ${slot.scene_name}`,
            emotion,
            sentiment: EMOTION_SENTIMENT[emotion as keyof typeof EMOTION_SENTIMENT] ?? 0,
            dayIndex: dayIdx,
            sceneIndex: sceneIdx,
          })
        })
      }
    })
    return series
  }, [trajectories])

  if (loading) {
    return (
      <div className="text-center py-20">
        <div className="inline-block w-6 h-6 border-2 border-amber border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!meta || trajectories.length === 0) {
    return (
      <div>
        <h1 className="text-xl font-medium mb-4">情绪轨迹</h1>
        <div className="text-center py-16 bg-white rounded-xl border border-gray-100">
          <p className="text-ink-light">还没有轨迹数据...</p>
          <p className="text-sm text-ink-light/60 mt-1">运行模拟后，情绪轨迹会出现在这里</p>
        </div>
      </div>
    )
  }

  const students = Object.entries(meta.agents).filter(([, a]) => a.role === 'student')
  const toggleAgent = (id: string) => {
    setSelectedAgents((prev) =>
      prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id]
    )
  }

  // SVG dimensions
  const width = 800
  const height = 300
  const padding = { top: 20, right: 20, bottom: 40, left: 40 }
  const chartW = width - padding.left - padding.right
  const chartH = height - padding.top - padding.bottom

  // Find max points for x scale
  const maxPoints = Math.max(...Object.values(agentSeries).map((s) => s.length), 1)

  return (
    <div>
      <h1 className="text-xl font-medium mb-1">情绪轨迹</h1>
      <p className="text-sm text-ink-light mb-4">选择角色，查看情绪随场景变化的曲线</p>

      {/* Agent selector */}
      <div className="flex flex-wrap gap-2 mb-4">
        {students.map(([id, agent]) => (
          <button
            key={id}
            onClick={() => toggleAgent(id)}
            className={`px-3 py-2 min-h-[44px] flex items-center rounded-full text-xs transition-colors ${
              selectedAgents.includes(id)
                ? 'bg-teal/15 text-teal font-medium'
                : 'bg-gray-50 text-ink-light hover:bg-gray-100'
            }`}
          >
            {agent.name}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full"
          style={{ minWidth: 600 }}
        >
          {/* Y axis labels */}
          <text x={padding.left - 8} y={padding.top + 10} textAnchor="end" fontSize="10" fill="#666">积极</text>
          <text x={padding.left - 8} y={padding.top + chartH / 2 + 4} textAnchor="end" fontSize="10" fill="#666">平静</text>
          <text x={padding.left - 8} y={padding.top + chartH - 2} textAnchor="end" fontSize="10" fill="#666">消极</text>

          {/* Grid lines */}
          <line
            x1={padding.left} y1={padding.top + chartH / 2}
            x2={padding.left + chartW} y2={padding.top + chartH / 2}
            stroke="#e5e5e5" strokeDasharray="4,4"
          />

          {/* Lines per agent */}
          {selectedAgents.map((agentId, agentIdx) => {
            const points = agentSeries[agentId]
            if (!points || points.length === 0) return null

            const colors = ['#5a8f7b', '#d4a853', '#D94848', '#8B6FB0', '#E8A838', '#FFD700', '#6B7B8D', '#E88B8B', '#FF8C42']
            const lineColor = colors[agentIdx % colors.length]

            const pathPoints = points.map((p, i) => {
              const x = padding.left + (i / Math.max(maxPoints - 1, 1)) * chartW
              const y = padding.top + (0.5 - p.sentiment * 0.5) * chartH
              return { x, y, point: p }
            })

            // Build smooth path
            const pathD = pathPoints.reduce((d, p, i) => {
              if (i === 0) return `M ${p.x} ${p.y}`
              const prev = pathPoints[i - 1]
              const cpx = (prev.x + p.x) / 2
              return d + ` C ${cpx} ${prev.y} ${cpx} ${p.y} ${p.x} ${p.y}`
            }, '')

            return (
              <g key={agentId}>
                <path d={pathD} fill="none" stroke={lineColor} strokeWidth="2" opacity="0.8" />
                {pathPoints.map((p, i) => (
                  <circle
                    key={i}
                    cx={p.x}
                    cy={p.y}
                    r={4}
                    fill={EMOTION_COLORS[p.point.emotion as keyof typeof EMOTION_COLORS] ?? '#B8B8B8'}
                    stroke="white"
                    strokeWidth={1.5}
                    className="cursor-pointer"
                    onMouseEnter={() => setHoveredPoint({ agentId, point: p.point, x: p.x, y: p.y })}
                    onMouseLeave={() => setHoveredPoint(null)}
                  />
                ))}
              </g>
            )
          })}

          {/* Tooltip */}
          {hoveredPoint && (
            <g>
              <rect
                x={hoveredPoint.x + 10}
                y={hoveredPoint.y - 40}
                width={160}
                height={36}
                rx={6}
                fill="white"
                stroke="#e5e5e5"
              />
              <text x={hoveredPoint.x + 18} y={hoveredPoint.y - 24} fontSize="11" fill="#2c2c2c">
                {meta.agents[hoveredPoint.agentId]?.name} · {hoveredPoint.point.scene}
              </text>
              <text x={hoveredPoint.x + 18} y={hoveredPoint.y - 10} fontSize="10" fill="#666">
                {EMOTION_LABELS[hoveredPoint.point.emotion as keyof typeof EMOTION_LABELS] ?? hoveredPoint.point.emotion}
              </text>
            </g>
          )}
        </svg>
      </div>
    </div>
  )
}
