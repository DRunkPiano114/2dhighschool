import { AnimatePresence } from 'framer-motion'
import type { Tick } from '../../lib/types'
import { useAppStore } from '../../stores/useAppStore'
import { SpeechBubble } from './SpeechBubble'
import { ThoughtBubble } from './ThoughtBubble'
import { WhisperLine } from './WhisperLine'
import { ActionLine } from './ActionLine'

interface TickBlockProps {
  tick: Tick
  names: Record<string, string>
}

export function TickBlock({ tick, names }: TickBlockProps) {
  const mindReading = useAppStore((s) => s.mindReadingEnabled)
  const { speech, actions, whispers, environmental_event, exits } = tick.public

  const isSilent = !speech && actions.length === 0 && whispers.length === 0 && exits.length === 0 && !environmental_event

  return (
    <div className="py-3 space-y-2">
      {/* Environmental event */}
      {environmental_event && (
        <p className="text-sm text-center text-ink-light bg-amber/5 rounded-lg py-2 px-4">
          {environmental_event}
        </p>
      )}

      {/* Speech */}
      {speech && (
        <>
          <SpeechBubble
            agentName={names[speech.agent] ?? speech.agent}
            targetName={speech.target ? (names[speech.target] ?? speech.target) : null}
            content={speech.content}
          />
          {/* Thought for the speaker */}
          <AnimatePresence>
            {mindReading && tick.minds[speech.agent] && (
              <ThoughtBubble
                agentName={names[speech.agent] ?? speech.agent}
                mind={tick.minds[speech.agent]}
                index={0}
              />
            )}
          </AnimatePresence>
        </>
      )}

      {/* Non-verbal actions */}
      {actions.map((action, i) => (
        <ActionLine
          key={i}
          agentName={names[action.agent] ?? action.agent}
          content={action.content}
          type={action.type}
        />
      ))}

      {/* Whispers */}
      {whispers.map((w, i) => (
        <WhisperLine
          key={i}
          fromName={names[w.from] ?? w.from}
          toName={names[w.to] ?? w.to}
          content={w.content}
          revealed={mindReading}
        />
      ))}

      {/* Exits */}
      {exits.map((agentId, i) => (
        <p key={i} className="ml-11 text-sm text-ink-light italic">
          {names[agentId] ?? agentId} 离开了
        </p>
      ))}

      {/* Silent tick */}
      {isSilent && (
        <p className="text-sm text-center text-ink-light/50 py-1">
          （安静）
          <span className="inline-flex gap-0.5 ml-1">
            <span className="w-1 h-1 rounded-full bg-ink-light/30 animate-pulse" />
            <span className="w-1 h-1 rounded-full bg-ink-light/30 animate-pulse" style={{ animationDelay: '0.3s' }} />
            <span className="w-1 h-1 rounded-full bg-ink-light/30 animate-pulse" style={{ animationDelay: '0.6s' }} />
          </span>
        </p>
      )}

      {/* Other minds (non-speaker observers) when mind reading is on */}
      <AnimatePresence>
        {mindReading && Object.entries(tick.minds)
          .filter(([id]) => id !== speech?.agent)
          .map(([id, mind], i) => (
            <ThoughtBubble
              key={id}
              agentName={names[id] ?? id}
              mind={mind}
              index={i + 1}
            />
          ))
        }
      </AnimatePresence>
    </div>
  )
}
