import type { SceneIndexEntry } from './types'

export interface TimeSlot {
  key: string
  time: string
  name: string
  scenes: SceneIndexEntry[]
}

/**
 * Group consecutive scenes that share time + name into a single time slot.
 * Used by the scene dropdown so viewers see "08:45 课间" once with
 * multi-location sub-items rather than duplicate labels.
 */
export function groupScenesByTimeSlot(scenes: SceneIndexEntry[]): TimeSlot[] {
  const slots: TimeSlot[] = []
  for (const scene of scenes) {
    const last = slots[slots.length - 1]
    if (last && last.time === scene.time && last.name === scene.name) {
      last.scenes.push(scene)
    } else {
      slots.push({
        key: `${scene.time}|${scene.name}`,
        time: scene.time,
        name: scene.name,
        scenes: [scene],
      })
    }
  }
  return slots
}
