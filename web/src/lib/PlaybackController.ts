import { useWorldStore } from '../stores/useWorldStore'
import { scoreGroup } from './drama'
import type { GroupData, PlaybackSpeed } from './types'

const BASE_TICK_MS = 3000 // 3s per tick at 1x

type Unsubscribe = () => void

/**
 * PlaybackController: one controller, two strategies (manual + broadcast).
 * Operates outside React — reads/writes store imperatively.
 * Camera state is NOT managed here (lives as PixiJS Container transform).
 */
export class PlaybackController {
  private timer: ReturnType<typeof setTimeout> | null = null
  private unsub: Unsubscribe | null = null

  start() {
    this.stop()
    // Subscribe to playback state changes
    this.unsub = useWorldStore.subscribe((state, prev) => {
      if (state.isPlaying !== prev.isPlaying ||
          state.playbackSpeed !== prev.playbackSpeed) {
        if (state.isPlaying) {
          this.scheduleNext(state.playbackSpeed)
        } else {
          this.clearTimer()
        }
      }
    })

    const { isPlaying, playbackSpeed } = useWorldStore.getState()
    if (isPlaying) this.scheduleNext(playbackSpeed)
  }

  stop() {
    this.clearTimer()
    this.unsub?.()
    this.unsub = null
  }

  private clearTimer() {
    if (this.timer) {
      clearTimeout(this.timer)
      this.timer = null
    }
  }

  private scheduleNext(speed: PlaybackSpeed) {
    this.clearTimer()
    this.timer = setTimeout(() => this.tick(), BASE_TICK_MS / speed)
  }

  private tick() {
    const state = useWorldStore.getState()
    if (!state.isPlaying || !state.currentSceneFile) return

    const group = state.currentSceneFile.groups[state.activeGroupIndex]
    if (!group || group.is_solo) {
      this.advanceGroup(state)
      return
    }

    const maxTick = group.ticks.length - 1
    if (state.currentTick < maxTick) {
      useWorldStore.setState({ currentTick: state.currentTick + 1 })
    } else {
      // End of group — advance
      this.advanceGroup(state)
    }

    this.scheduleNext(state.playbackSpeed)
  }

  private advanceGroup(state: ReturnType<typeof useWorldStore.getState>) {
    if (!state.currentSceneFile) return
    const groups = state.currentSceneFile.groups

    if (state.mode === 'broadcast') {
      // Find next non-solo group with drama
      const sortedGroups = this.groupsByDrama(groups)
      const currentIdx = sortedGroups.findIndex(
        (_, i) => sortedGroups[i] === groups[state.activeGroupIndex]
      )
      const nextIdx = currentIdx + 1
      if (nextIdx < sortedGroups.length) {
        const realIdx = groups.indexOf(sortedGroups[nextIdx])
        useWorldStore.setState({ activeGroupIndex: realIdx, currentTick: 0 })
        this.scheduleNext(state.playbackSpeed)
        return
      }
    } else {
      // Manual: advance to next group
      if (state.activeGroupIndex < groups.length - 1) {
        useWorldStore.setState({
          activeGroupIndex: state.activeGroupIndex + 1,
          currentTick: 0,
        })
        this.scheduleNext(state.playbackSpeed)
        return
      }
    }

    // End of scene — advance to next scene
    this.advanceScene(state)
  }

  private advanceScene(state: ReturnType<typeof useWorldStore.getState>) {
    const nextIdx = state.currentSceneIndex + 1
    if (nextIdx < state.scenes.length) {
      useWorldStore.getState().setCurrentSceneIndex(nextIdx)
      this.scheduleNext(state.playbackSpeed)
    } else {
      // End of day
      useWorldStore.setState({ isPlaying: false })
    }
  }

  private groupsByDrama(groups: GroupData[]): GroupData[] {
    return [...groups]
      .filter(g => !g.is_solo)
      .sort((a, b) => scoreGroup(b) - scoreGroup(a))
  }
}

/** Singleton instance */
export const playbackController = new PlaybackController()
