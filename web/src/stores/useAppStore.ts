import { create } from 'zustand'

interface AppState {
  currentDay: string
  currentSceneIndex: number
  activeGroupIndex: number
  mindReadingEnabled: boolean
  focusedAgent: string | null

  setCurrentDay: (day: string) => void
  setCurrentSceneIndex: (index: number) => void
  setActiveGroupIndex: (index: number) => void
  toggleMindReading: () => void
  setFocusedAgent: (agentId: string | null) => void
}

export const useAppStore = create<AppState>((set) => ({
  currentDay: 'day_001',
  currentSceneIndex: 0,
  activeGroupIndex: 0,
  mindReadingEnabled: false,
  focusedAgent: null,

  setCurrentDay: (day) => set({ currentDay: day, currentSceneIndex: 0, activeGroupIndex: 0 }),
  setCurrentSceneIndex: (index) => set({ currentSceneIndex: index, activeGroupIndex: 0 }),
  setActiveGroupIndex: (index) => set({ activeGroupIndex: index }),
  toggleMindReading: () => set((s) => ({ mindReadingEnabled: !s.mindReadingEnabled })),
  setFocusedAgent: (agentId) => set({ focusedAgent: agentId }),
}))
