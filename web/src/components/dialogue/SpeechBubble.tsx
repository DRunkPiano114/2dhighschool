interface SpeechBubbleProps {
  agentName: string
  targetName?: string | null
  content: string
}

export function SpeechBubble({ agentName, targetName, content }: SpeechBubbleProps) {
  return (
    <div className="flex gap-3 items-start">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-teal/20 flex items-center justify-center text-sm font-medium text-teal">
        {agentName[0]}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 mb-1">
          <span className="font-medium text-sm text-ink">{agentName}</span>
          {targetName && (
            <span className="text-xs text-ink-light">→ {targetName}</span>
          )}
        </div>
        <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-2.5 border border-gray-100 shadow-sm">
          <p className="text-sm leading-relaxed">{content}</p>
        </div>
      </div>
    </div>
  )
}
