import type { Academics } from '../../lib/types'

const RANK_COLORS: Record<string, string> = {
  '上游': 'bg-emerald-100 text-emerald-700',
  '中上': 'bg-teal-100 text-teal-700',
  '中游': 'bg-amber-100 text-amber-700',
  '中下': 'bg-orange-100 text-orange-700',
  '下游': 'bg-red-100 text-red-700',
}

export function AcademicsBadge({ academics }: { academics: Academics }) {
  const rankClass = RANK_COLORS[academics.overall_rank] ?? 'bg-gray-100 text-gray-700'

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${rankClass}`}>
          {academics.overall_rank}
        </span>
        <span className="text-xs text-ink-light">→ {academics.target}</span>
      </div>
      <div className="flex gap-1 flex-wrap">
        {academics.strengths.map((s) => (
          <span key={s} className="px-1.5 py-0.5 rounded text-xs bg-emerald-50 text-emerald-600">
            ✓ {s}
          </span>
        ))}
        {academics.weaknesses.map((w) => (
          <span key={w} className="px-1.5 py-0.5 rounded text-xs bg-red-50 text-red-500">
            ✗ {w}
          </span>
        ))}
      </div>
      <p className="text-xs text-ink-light">{academics.study_attitude}</p>
    </div>
  )
}
