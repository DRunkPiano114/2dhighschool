interface ActionLineProps {
  agentName: string
  content: string | null
  type: string
}

export function ActionLine({ agentName, content, type }: ActionLineProps) {
  if (!content) return null

  if (type === 'exit') {
    return (
      <p className="ml-11 text-sm text-ink-light italic my-1">
        {agentName} 离开了
      </p>
    )
  }

  return (
    <p className="ml-11 text-sm text-ink-light italic my-1">
      *{agentName} {content}*
    </p>
  )
}
