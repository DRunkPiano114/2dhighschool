import { create } from 'zustand'
import type { RoomId, SceneIndexEntry, SceneFile, Meta, SceneGroup } from '../lib/types'
import type { ChatMessage, AgentReaction } from '../lib/chat'
import { findFirstSpeechTick } from '../components/narrative/focal'

export type ChatMode = 'off' | 'god' | 'roleplay'

interface WorldState {
  // --- data ---
  meta: Meta | null
  scenes: SceneIndexEntry[]
  currentSceneFile: SceneFile | null

  // --- navigation ---
  currentDay: string
  currentSceneIndex: number
  activeGroupIndex: number
  currentTick: number
  currentRoom: RoomId

  // --- focus ---
  focusedAgent: string | null
  sidePanelOpen: boolean

  // --- chat ---
  chatMode: ChatMode
  chatMessages: ChatMessage[]
  chatStreaming: boolean
  chatStreamBuffer: string
  rolePlayUserAgent: string | null
  rolePlayTargetAgents: string[]
  rolePlayReactions: AgentReaction[]

  // --- actions ---
  setMeta: (meta: Meta) => void
  setScenes: (scenes: SceneIndexEntry[]) => void
  setCurrentSceneFile: (file: SceneFile | null) => void
  setCurrentDay: (day: string) => void
  setCurrentSceneIndex: (index: number) => void
  setActiveGroupIndex: (index: number) => void
  setCurrentTick: (tick: number) => void
  setCurrentRoom: (room: RoomId) => void
  setFocusedAgent: (agentId: string | null) => void
  setSidePanelOpen: (open: boolean) => void
  advanceTick: () => void
  retreatTick: () => void
  goNext: () => void
  goPrev: () => void

  // --- chat actions ---
  openGodModeChat: (agentId: string) => void
  openRolePlayChat: (userAgentId: string, targets: string[]) => void
  closeChat: () => void
  appendChatMessage: (msg: ChatMessage) => void
  setChatStreaming: (streaming: boolean) => void
  appendStreamToken: (token: string) => void
  flushStreamBuffer: () => void
  appendAgentReaction: (reaction: AgentReaction) => void
}

export const useWorldStore = create<WorldState>((set, get) => ({
  meta: null,
  scenes: [],
  currentSceneFile: null,

  currentDay: 'day_001',
  currentSceneIndex: 0,
  activeGroupIndex: 0,
  currentTick: 0,
  currentRoom: '教室',

  focusedAgent: null,
  sidePanelOpen: false,

  chatMode: 'off',
  chatMessages: [],
  chatStreaming: false,
  chatStreamBuffer: '',
  rolePlayUserAgent: null,
  rolePlayTargetAgents: [],
  rolePlayReactions: [],

  setMeta: (meta) => set({ meta }),
  setScenes: (scenes) => set({ scenes }),

  setCurrentSceneFile: (file) => {
    if (file) {
      const firstGroup = file.groups[0]
      set({
        currentSceneFile: file,
        currentTick: findFirstSpeechTick(firstGroup),
      })
    } else {
      set({ currentSceneFile: null, currentTick: 0 })
    }
  },

  setCurrentDay: (day) => set({
    currentDay: day,
    currentSceneIndex: 0,
    activeGroupIndex: 0,
    currentTick: 0,
  }),

  setCurrentSceneIndex: (index) => {
    const { scenes } = get()
    const scene = scenes[index]
    set({
      currentSceneIndex: index,
      activeGroupIndex: 0,
      currentTick: 0,
      currentRoom: (scene?.location as RoomId) ?? '教室',
    })
  },

  setActiveGroupIndex: (index) => {
    const file = get().currentSceneFile
    const group = file?.groups[index]
    set({
      activeGroupIndex: index,
      currentTick: findFirstSpeechTick(group),
    })
  },

  setCurrentTick: (tick) => set({ currentTick: tick }),
  setCurrentRoom: (room) => set({ currentRoom: room }),

  setFocusedAgent: (agentId) => set({
    focusedAgent: agentId,
    sidePanelOpen: agentId !== null,
  }),

  setSidePanelOpen: (open) => set({
    sidePanelOpen: open,
    focusedAgent: open ? get().focusedAgent : null,
  }),

  advanceTick: () => {
    const { currentTick, currentSceneFile, activeGroupIndex } = get()
    if (!currentSceneFile) return
    const group = currentSceneFile.groups[activeGroupIndex]
    if (!group || group.is_solo) return
    const maxTick = group.ticks.length - 1
    if (currentTick < maxTick) {
      set({ currentTick: currentTick + 1 })
    }
  },

  retreatTick: () => {
    const { currentTick } = get()
    if (currentTick > 0) {
      set({ currentTick: currentTick - 1 })
    }
  },

  // Cross-group / cross-scene navigation. At a tick boundary, jumps to the
  // adjacent group (first speech tick) or scene (group 0, first speech tick),
  // so ←/→ never gets stuck mid-conversation.
  goNext: () => {
    const { currentTick, currentSceneFile, activeGroupIndex, scenes, currentSceneIndex } = get()
    if (!currentSceneFile) return
    const group = currentSceneFile.groups[activeGroupIndex]
    const ticks = group && !group.is_solo ? (group as SceneGroup).ticks : []
    if (ticks.length > 0 && currentTick < ticks.length - 1) {
      set({ currentTick: currentTick + 1 })
      return
    }
    if (activeGroupIndex < currentSceneFile.groups.length - 1) {
      const next = currentSceneFile.groups[activeGroupIndex + 1]
      set({ activeGroupIndex: activeGroupIndex + 1, currentTick: findFirstSpeechTick(next) })
      return
    }
    if (currentSceneIndex < scenes.length - 1) {
      get().setCurrentSceneIndex(currentSceneIndex + 1)
    }
  },

  goPrev: () => {
    const { currentTick, currentSceneFile, activeGroupIndex, currentSceneIndex } = get()
    if (!currentSceneFile) return
    if (currentTick > 0) {
      set({ currentTick: currentTick - 1 })
      return
    }
    if (activeGroupIndex > 0) {
      const prev = currentSceneFile.groups[activeGroupIndex - 1]
      set({ activeGroupIndex: activeGroupIndex - 1, currentTick: findFirstSpeechTick(prev) })
      return
    }
    if (currentSceneIndex > 0) {
      get().setCurrentSceneIndex(currentSceneIndex - 1)
    }
  },

  // --- chat actions ---
  openGodModeChat: (agentId) => set({
    chatMode: 'god',
    chatMessages: [],
    chatStreaming: false,
    chatStreamBuffer: '',
    focusedAgent: agentId,
    sidePanelOpen: false,
    rolePlayReactions: [],
  }),

  openRolePlayChat: (userAgentId, targets) => set({
    chatMode: 'roleplay',
    chatMessages: [],
    chatStreaming: false,
    chatStreamBuffer: '',
    rolePlayUserAgent: userAgentId,
    rolePlayTargetAgents: targets,
    rolePlayReactions: [],
  }),

  closeChat: () => set({
    chatMode: 'off',
    chatMessages: [],
    chatStreaming: false,
    chatStreamBuffer: '',
    rolePlayUserAgent: null,
    rolePlayTargetAgents: [],
    rolePlayReactions: [],
  }),

  appendChatMessage: (msg) => set((s) => ({
    chatMessages: [...s.chatMessages, msg],
  })),

  setChatStreaming: (streaming) => set({ chatStreaming: streaming }),

  appendStreamToken: (token) => set((s) => ({
    chatStreamBuffer: s.chatStreamBuffer + token,
  })),

  flushStreamBuffer: () => {
    const { chatStreamBuffer } = get()
    if (!chatStreamBuffer) return
    set((s) => ({
      chatMessages: [...s.chatMessages, {
        role: 'assistant',
        content: chatStreamBuffer,
      }],
      chatStreamBuffer: '',
    }))
  },

  appendAgentReaction: (reaction) => set((s) => ({
    rolePlayReactions: [...s.rolePlayReactions, reaction],
    chatMessages: [...s.chatMessages, {
      role: reaction.agent_id,
      content: reaction.content,
      agent_name: reaction.agent_name,
    }],
  })),
}))
