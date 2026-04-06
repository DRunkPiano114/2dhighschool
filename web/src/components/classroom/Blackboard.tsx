interface BlackboardProps {
  currentDate: string
  examCountdown: number
}

export function Blackboard({ currentDate, examCountdown }: BlackboardProps) {
  // Format "2025-09-01" → "2025年9月1日"
  const formatted = currentDate.replace(
    /(\d{4})-(\d{2})-(\d{2})/,
    (_, y, m, d) => `${y}年${parseInt(m)}月${parseInt(d)}日`
  )

  return (
    <div className="bg-emerald-900 rounded-lg px-8 py-6 shadow-lg relative overflow-hidden">
      {/* Chalk dust texture */}
      <div className="absolute inset-0 opacity-5 bg-gradient-to-b from-white/20 to-transparent" />

      <div className="relative flex items-center justify-between">
        <div>
          <h1 className="chalk-text text-2xl font-bold tracking-wider">高三(2)班</h1>
          <p className="chalk-text text-sm mt-1 opacity-80">{formatted}</p>
        </div>
        <div className="text-right">
          <p className="chalk-text text-sm opacity-70">距离期中考试还有</p>
          <p className="chalk-text text-3xl font-bold">{examCountdown} <span className="text-lg">天</span></p>
        </div>
      </div>
    </div>
  )
}
