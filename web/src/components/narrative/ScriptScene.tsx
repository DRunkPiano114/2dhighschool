import type { ReactNode } from 'react'
import { useWorldStore } from '../../stores/useWorldStore'
import { EMOTION_COLORS, EMOTION_LABELS } from '../../lib/constants'
import type { SceneFile, SceneInfo, Tick, Emotion } from '../../lib/types'

const URGENCY_THRESHOLD = 4

type LineKind = 'action' | 'speech' | 'thought'

export function ScriptScene() {
  const sceneFile = useWorldStore(s => s.currentSceneFile)
  const groupIdx = useWorldStore(s => s.activeGroupIndex)

  if (!sceneFile) {
    return <div className="script-stage script-loading">…</div>
  }

  const group = sceneFile.groups[groupIdx]
  const sceneInfo = sceneFile.scene
  const names = sceneFile.participant_names

  if (!group) {
    return (
      <div className="script-stage">
        <div className="script-page">
          <ScriptHead
            sceneInfo={sceneInfo}
            groupTitle=""
            groupParticipants={[]}
            names={names}
          />
          <p className="script-loading">（无内容）</p>
        </div>
      </div>
    )
  }

  if (group.is_solo) {
    const aid = group.participants[0]
    return (
      <div className="script-stage">
        <div className="script-page">
          <ScriptHead
            sceneInfo={sceneInfo}
            groupTitle="独白"
            groupParticipants={group.participants}
            names={names}
          />
          <div className="script-body">
            <div className="script-tick">
              <ScriptLine
                kind="thought"
                speakerName={names[aid] ?? aid}
                content={group.solo_reflection.inner_thought}
                emotion={group.solo_reflection.emotion}
              />
              {group.solo_reflection.activity && (
                <ScriptLine
                  kind="action"
                  speakerName={names[aid] ?? aid}
                  content={group.solo_reflection.activity}
                />
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="script-stage">
      <div className="script-page">
        <ScriptHead
          sceneInfo={sceneInfo}
          groupTitle={`G${group.group_index}`}
          groupParticipants={group.participants}
          names={names}
        />
        <ScriptBody ticks={group.ticks} names={names} />
      </div>
    </div>
  )
}

interface ScriptHeadProps {
  sceneInfo: SceneInfo
  groupTitle: string
  groupParticipants: string[]
  names: SceneFile['participant_names']
}

function ScriptHead({ sceneInfo, groupTitle, groupParticipants, names }: ScriptHeadProps) {
  const participantNames = groupParticipants.map(p => names[p] ?? p).join(' / ')
  return (
    <header className="script-scene-head">
      <h1>【{sceneInfo.name} · {sceneInfo.location} · {sceneInfo.time}】</h1>
      {sceneInfo.description && (
        <p className="script-scene-subtitle">{sceneInfo.description}</p>
      )}
      {groupTitle && (
        <p className="script-scene-group">—— {groupTitle} · {participantNames}</p>
      )}
    </header>
  )
}

interface ScriptBodyProps {
  ticks: Tick[]
  names: SceneFile['participant_names']
}

function ScriptBody({ ticks, names }: ScriptBodyProps) {
  // Track per-agent emotion across ticks so the colored dot only appears
  // when the emotion changes (or on the agent's first appearance).
  const lastEmotion: Record<string, Emotion | undefined> = {}

  const dotIfChanged = (agentId: string, emotion: Emotion | undefined): Emotion | undefined => {
    if (!emotion) return undefined
    if (lastEmotion[agentId] === emotion) return undefined
    lastEmotion[agentId] = emotion
    return emotion
  }

  return (
    <div className="script-body">
      {ticks.map((tick, idx) => {
        const lines: ReactNode[] = []
        const speakerId = tick.public.speech?.agent ?? null
        const targetId = tick.public.speech?.target ?? null

        // 1. environmental event (rare)
        if (tick.public.environmental_event) {
          lines.push(
            <p key={`env-${idx}`} className="script-env">
              {tick.public.environmental_event}
            </p>
          )
        }

        // 2. visible non-verbal actions
        for (const [actIdx, action] of tick.public.actions.entries()) {
          if (!action.content) continue
          const mind = tick.minds[action.agent]
          lines.push(
            <ScriptLine
              key={`act-${idx}-${actIdx}`}
              kind="action"
              speakerName={names[action.agent] ?? action.agent}
              content={action.content}
              emotion={dotIfChanged(action.agent, mind?.emotion)}
            />
          )
        }

        // 3. public speech
        if (tick.public.speech) {
          const s = tick.public.speech
          const mind = tick.minds[s.agent]
          lines.push(
            <ScriptLine
              key={`speech-${idx}`}
              kind="speech"
              speakerName={names[s.agent] ?? s.agent}
              content={s.content}
              emotion={dotIfChanged(s.agent, mind?.emotion)}
            />
          )
        }

        // 4. inner thoughts — speaker / target always; others gated by urgency
        // or disruptive flag. Iterate in a stable order: speaker → target →
        // remaining participants (insertion order from minds object).
        const orderedAgents: string[] = []
        if (speakerId && tick.minds[speakerId]) orderedAgents.push(speakerId)
        if (targetId && targetId !== speakerId && tick.minds[targetId]) orderedAgents.push(targetId)
        for (const aid of Object.keys(tick.minds)) {
          if (!orderedAgents.includes(aid)) orderedAgents.push(aid)
        }

        for (const aid of orderedAgents) {
          const mind = tick.minds[aid]
          if (!mind?.inner_thought) continue
          const isSpeaker = aid === speakerId
          const isTarget = aid === targetId
          const passes =
            isSpeaker || isTarget || mind.is_disruptive || mind.urgency >= URGENCY_THRESHOLD
          if (!passes) continue

          lines.push(
            <ScriptLine
              key={`thought-${idx}-${aid}`}
              kind="thought"
              speakerName={names[aid] ?? aid}
              content={mind.inner_thought}
              emotion={dotIfChanged(aid, mind.emotion)}
            />
          )
        }

        if (lines.length === 0) return null
        return <div key={idx} className="script-tick">{lines}</div>
      })}
    </div>
  )
}

interface ScriptLineProps {
  kind: LineKind
  speakerName: string
  content: string
  emotion?: Emotion
}

function ScriptLine({ kind, speakerName, content, emotion }: ScriptLineProps) {
  return (
    <div className={`script-line script-line-${kind}`}>
      <div className="script-name-col">
        {emotion && (
          <span
            className="script-emotion-dot"
            title={EMOTION_LABELS[emotion]}
            style={{ background: EMOTION_COLORS[emotion] }}
          />
        )}
        <span className="script-name">{speakerName}</span>
      </div>
      <div className="script-content-col">
        {kind === 'speech' && <>“{content}”</>}
        {kind === 'action' && <>（{content}）</>}
        {kind === 'thought' && <>〔{content}〕</>}
      </div>
    </div>
  )
}
