import type { Meta, Agent, SceneIndexEntry, SceneFile, GameEvent, DayTrajectory } from './types'

const cache = new Map<string, unknown>()

async function fetchJson<T>(url: string): Promise<T> {
  const cached = cache.get(url)
  if (cached) return cached as T
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`)
  const data = await res.json()
  cache.set(url, data)
  return data as T
}

export function loadMeta(): Promise<Meta> {
  return fetchJson<Meta>('/data/meta.json')
}

export function loadAgent(id: string): Promise<Agent> {
  return fetchJson<Agent>(`/data/agents/${id}/profile.json`)
}

export function loadScenes(day: string): Promise<SceneIndexEntry[]> {
  return fetchJson<SceneIndexEntry[]>(`/data/days/${day}/scenes.json`)
}

export function loadSceneFile(day: string, filename: string): Promise<SceneFile> {
  return fetchJson<SceneFile>(`/data/days/${day}/${filename}`)
}

export function loadTrajectory(day: string): Promise<DayTrajectory> {
  return fetchJson<DayTrajectory>(`/data/days/${day}/trajectory.json`)
}

export function loadEvents(): Promise<GameEvent[]> {
  return fetchJson<GameEvent[]>('/data/events.json')
}

export interface AgentColors {
  [agentId: string]: {
    main_color: string
    accent_color?: string
    motif_emoji?: string
  }
}

export function loadAgentColors(): Promise<AgentColors> {
  return fetchJson<AgentColors>('/data/agent_colors.json')
}

export interface TilesetManifest {
  [category: string]: {
    [name: string]: { w: number; h: number; tiles_w: number; tiles_h: number }
  }
}

export function loadTilesetManifest(): Promise<TilesetManifest> {
  return fetchJson<TilesetManifest>('/data/tilesets/manifest.json')
}

export interface AnimatedManifest {
  [name: string]: { frame_w: number; frame_h: number; count: number; fps: number }
}

export function loadAnimatedManifest(): Promise<AnimatedManifest> {
  return fetchJson<AnimatedManifest>('/data/animated/manifest.json')
}

/** Prefetch all scene files for a day (~650KB). Fire-and-forget. */
export async function prefetchDay(day: string): Promise<void> {
  const scenes = await loadScenes(day)
  await Promise.all(scenes.map(s => loadSceneFile(day, s.file)))
}
