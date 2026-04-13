import type { Tick, SceneIndexEntry } from './types'

/**
 * Drama score for a single tick.
 * Formula: speak*1 + disruptive*5 + urgency*0.5 + exit*2
 */
export function scoreTick(tick: Tick): number {
  const p = tick.public
  const speakCount = p.speech ? 1 : 0
  const exitCount = p.exits.length

  const minds = Object.values(tick.minds)
  const disruptiveCount = minds.filter(m => m.is_disruptive).length
  const maxUrgency = minds.length > 0
    ? Math.max(...minds.map(m => m.urgency))
    : 0

  return (
    speakCount * 1 +
    disruptiveCount * 5 +
    maxUrgency * 0.5 +
    exitCount * 2
  )
}

/** Top 20% drama threshold for a list of tick scores. */
export function dramaThreshold(scores: number[]): number {
  if (scores.length === 0) return 0
  const sorted = [...scores].sort((a, b) => b - a)
  const idx = Math.max(0, Math.floor(sorted.length * 0.2) - 1)
  return sorted[idx]
}

/** Is this tick a drama peak within the given group? */
export function isDramaPeak(tick: Tick, allScores: number[]): boolean {
  return scoreTick(tick) >= dramaThreshold(allScores)
}

/**
 * Sort scene entries by aggregate drama (highest first).
 * Scenes at the same time slot are grouped together.
 * Solo-only scenes go to the end.
 */
export function sortScenesByDrama(
  scenes: SceneIndexEntry[],
  sceneScores: Map<string, number>,
): SceneIndexEntry[] {
  return [...scenes].sort((a, b) => {
    if (a.time === b.time) {
      const aAllSolo = a.groups.every(g => g.is_solo)
      const bAllSolo = b.groups.every(g => g.is_solo)
      if (aAllSolo !== bAllSolo) return aAllSolo ? 1 : -1
      return (sceneScores.get(b.file) ?? 0) - (sceneScores.get(a.file) ?? 0)
    }
    return a.time.localeCompare(b.time)
  })
}
