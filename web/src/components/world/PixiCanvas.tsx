import { Application, extend, useApplication, useTick } from '@pixi/react'
import { Container, Graphics } from 'pixi.js'
import { useCallback, useEffect, useRef } from 'react'
import { useWorldStore } from '../../stores/useWorldStore'
import { loadMeta, loadScenes, loadSceneFile, prefetchDay } from '../../lib/data'
import { ROOMS, TILE, derivePositions } from '../../lib/roomConfig'
import { createCharacterSprite, updateSpriteState } from './CharacterSprite'
import { Camera } from './Camera'
import { BubbleOverlay, type BubbleData } from './BubbleOverlay'
import { DanmuLayer } from './DanmuLayer'
import { pickDanmu } from '../../lib/drama'
import { Room } from './Room'
import { TopBar } from '../ui/TopBar'
import { BottomBar } from '../ui/BottomBar'
import { RoomNav } from '../ui/RoomNav'
import { SidePanel } from '../ui/SidePanel'
import { playbackController } from '../../lib/PlaybackController'
import type { SceneGroup } from '../../lib/types'

extend({ Container, Graphics })

// --- data loading ---

function useDataLoader() {
  const setMeta = useWorldStore(s => s.setMeta)
  const setScenes = useWorldStore(s => s.setScenes)
  const setSceneFile = useWorldStore(s => s.setCurrentSceneFile)
  const setSceneIdx = useWorldStore(s => s.setCurrentSceneIndex)
  const currentDay = useWorldStore(s => s.currentDay)
  const sceneIdx = useWorldStore(s => s.currentSceneIndex)
  const scenes = useWorldStore(s => s.scenes)

  // Load meta once
  useEffect(() => {
    loadMeta().then(m => {
      setMeta(m)
    })
  }, [setMeta])

  // Load scenes when day changes
  useEffect(() => {
    loadScenes(currentDay).then(s => {
      setScenes(s)
      if (s.length > 0) setSceneIdx(0)
    })
    prefetchDay(currentDay).catch(() => {})
  }, [currentDay, setScenes, setSceneIdx])

  // Load scene file when scene index changes
  useEffect(() => {
    const entry = scenes[sceneIdx]
    if (!entry) return
    loadSceneFile(currentDay, entry.file).then(setSceneFile)
  }, [currentDay, sceneIdx, scenes, setSceneFile])
}

// --- world scene ---

function WorldScene() {
  const { app } = useApplication()
  const currentRoom = useWorldStore(s => s.currentRoom)
  const sceneFile = useWorldStore(s => s.currentSceneFile)
  const groupIdx = useWorldStore(s => s.activeGroupIndex)
  const currentTick = useWorldStore(s => s.currentTick)
  const mindReading = useWorldStore(s => s.mindReadingEnabled)
  const focusedAgent = useWorldStore(s => s.focusedAgent)
  const mode = useWorldStore(s => s.mode)
  const meta = useWorldStore(s => s.meta)

  const worldRef = useRef<Container | null>(null)
  const cameraRef = useRef<Camera | null>(null)
  const spritesRef = useRef(new Map<string, Container>())
  const bubbleRef = useRef<BubbleOverlay | null>(null)
  const danmuRef = useRef<DanmuLayer | null>(null)
  const prevTickRef = useRef(-1)

  // Init camera, bubble overlay, danmu layer
  useEffect(() => {
    const canvas = app.canvas as HTMLCanvasElement
    const parent = canvas.parentElement
    if (!parent) return

    // Wrap canvas in relative container for overlays
    let wrapper = parent.querySelector('.pixi-wrapper') as HTMLDivElement | null
    if (!wrapper) {
      wrapper = document.createElement('div')
      wrapper.className = 'pixi-wrapper'
      Object.assign(wrapper.style, {
        position: 'relative',
        width: `${canvas.width}px`,
        height: `${canvas.height}px`,
      })
      parent.insertBefore(wrapper, canvas)
      wrapper.appendChild(canvas)
    }

    bubbleRef.current = new BubbleOverlay(wrapper)
    danmuRef.current = new DanmuLayer(wrapper)

    return () => {
      bubbleRef.current?.destroy()
      danmuRef.current?.destroy()
    }
  }, [app])

  // Setup world container with camera
  const worldContainerRef = useCallback((node: Container | null) => {
    worldRef.current = node
    if (node && app.canvas) {
      const cam = new Camera(node, app.canvas.width, app.canvas.height)
      const room = ROOMS[currentRoom]
      cam.jumpTo((room.cols * TILE) / 2, (room.rows * TILE) / 2, 1)
      cameraRef.current = cam
    }
  }, [app, currentRoom])

  // Manage character sprites
  useEffect(() => {
    const world = worldRef.current
    if (!world || !sceneFile) return

    // Clear old sprites
    for (const s of spritesRef.current.values()) s.destroy({ children: true })
    spritesRef.current.clear()

    const group = sceneFile.groups[groupIdx]
    if (!group) return

    const positions = derivePositions(
      currentRoom,
      group.participants,
      groupIdx,
      meta?.agents as Record<string, { seat_number: number | null }>,
    )

    for (const agentId of group.participants) {
      const name = sceneFile.participant_names[agentId] ?? agentId
      const sprite = createCharacterSprite(agentId, name)
      const pos = positions[agentId]
      if (pos) {
        sprite.x = pos.x
        sprite.y = pos.y
      }
      sprite.eventMode = 'static'
      sprite.cursor = 'pointer'
      sprite.on('pointertap', () => {
        useWorldStore.getState().setFocusedAgent(agentId)
      })
      world.addChild(sprite)
      spritesRef.current.set(agentId, sprite)
    }

    // Also add other groups' characters (dimmed)
    for (let gi = 0; gi < sceneFile.groups.length; gi++) {
      if (gi === groupIdx) continue
      const otherGroup = sceneFile.groups[gi]
      const otherPos = derivePositions(
        currentRoom,
        otherGroup.participants,
        gi,
        meta?.agents as Record<string, { seat_number: number | null }>,
      )
      for (const agentId of otherGroup.participants) {
        if (spritesRef.current.has(agentId)) continue
        const name = sceneFile.participant_names[agentId] ?? agentId
        const sprite = createCharacterSprite(agentId, name)
        const pos = otherPos[agentId]
        if (pos) { sprite.x = pos.x; sprite.y = pos.y }
        sprite.alpha = 0.35
        sprite.eventMode = 'static'
        sprite.cursor = 'pointer'
        sprite.on('pointertap', () => {
          useWorldStore.getState().setFocusedAgent(agentId)
        })
        world.addChild(sprite)
        spritesRef.current.set(agentId, sprite)
      }
    }
  }, [sceneFile, groupIdx, currentRoom, meta])

  // Update sprites + bubbles per tick
  useEffect(() => {
    if (!sceneFile) return
    const group = sceneFile.groups[groupIdx]
    if (!group || group.is_solo) {
      bubbleRef.current?.setBubbles([])
      // Solo: show thought bubble
      if (group?.is_solo) {
        const solo = group
        const name = sceneFile.participant_names[solo.participants[0]] ?? ''
        bubbleRef.current?.setBubbles([{
          agentId: solo.participants[0],
          displayName: name,
          text: solo.solo_reflection.inner_thought,
          type: 'thought',
        }])
      }
      return
    }

    const tick = (group as SceneGroup).ticks[currentTick]
    if (!tick) return

    // Update sprite states
    for (const [agentId, sprite] of spritesRef.current) {
      const mind = tick.minds[agentId]
      const isActiveGroup = group.participants.includes(agentId)
      const isFocused = focusedAgent === null || focusedAgent === agentId
      const state = mind?.action_type === 'speak' ? 'talking'
        : mind?.action_type === 'whisper' ? 'whispering'
        : 'idle'
      updateSpriteState(sprite, state as 'idle' | 'talking' | 'whispering', !isActiveGroup || !isFocused)
    }

    // Build bubbles
    const bubbles: BubbleData[] = []

    // Speech bubble
    if (tick.public.speech) {
      const s = tick.public.speech
      bubbles.push({
        agentId: s.agent,
        displayName: sceneFile.participant_names[s.agent] ?? '',
        text: s.content,
        type: 'speech',
        target: s.target ?? undefined,
      })
    }

    // Whisper notices
    for (const w of tick.public.whispers) {
      const fromName = sceneFile.participant_names[w.from] ?? ''
      const toName = sceneFile.participant_names[w.to] ?? ''
      bubbles.push({
        agentId: w.from,
        displayName: fromName,
        text: mindReading ? w.content : `${fromName}对${toName}说了悄悄话`,
        type: mindReading ? 'speech' : 'whisper_notice',
        target: w.to,
      })
    }

    // Thought bubbles (mind reading)
    if (mindReading) {
      for (const [agentId, mind] of Object.entries(tick.minds)) {
        // Don't duplicate speaker's bubble
        if (tick.public.speech?.agent === agentId) continue
        if (tick.public.whispers.some(w => w.from === agentId)) continue
        bubbles.push({
          agentId,
          displayName: sceneFile.participant_names[agentId] ?? '',
          text: mind.inner_thought,
          type: 'thought',
        })
      }
    }

    bubbleRef.current?.setBubbles(bubbles)

    // Danmu in broadcast mode
    if (mode === 'broadcast' && prevTickRef.current !== currentTick) {
      const danmuTexts = pickDanmu(tick)
      if (danmuTexts.length > 0) danmuRef.current?.fire(danmuTexts)
    }
    prevTickRef.current = currentTick
  }, [sceneFile, groupIdx, currentTick, mindReading, focusedAgent, mode])

  // Camera: center on room when room changes
  useEffect(() => {
    const room = ROOMS[currentRoom]
    if (room && cameraRef.current) {
      cameraRef.current.panTo((room.cols * TILE) / 2, (room.rows * TILE) / 2)
    }
  }, [currentRoom])

  // Ticker: update camera + bubble positions
  useTick(() => {
    cameraRef.current?.update()
    if (worldRef.current) {
      bubbleRef.current?.updatePositions(spritesRef.current, worldRef.current)
    }
  })

  // Mouse handlers for explore mode camera
  useEffect(() => {
    const canvas = app.canvas as HTMLCanvasElement
    const cam = cameraRef.current
    if (!cam || mode !== 'explore') return

    const onDown = (e: PointerEvent) => cam.onPointerDown(e.clientX, e.clientY)
    const onMove = (e: PointerEvent) => cam.onPointerMove(e.clientX, e.clientY)
    const onUp = () => cam.onPointerUp()
    const onWheel = (e: WheelEvent) => { e.preventDefault(); cam.onWheel(e.deltaY) }

    canvas.addEventListener('pointerdown', onDown)
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    canvas.addEventListener('wheel', onWheel, { passive: false })

    return () => {
      canvas.removeEventListener('pointerdown', onDown)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      canvas.removeEventListener('wheel', onWheel)
    }
  }, [app, mode])

  // Keyboard controls
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const store = useWorldStore.getState()
      if (e.key === 'ArrowRight') store.advanceTick()
      else if (e.key === 'ArrowLeft') store.retreatTick()
      else if (e.key === ' ') { e.preventDefault(); store.setIsPlaying(!store.isPlaying) }
      else if (e.key === 'm' || e.key === 'M') store.toggleMindReading()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <pixiContainer ref={worldContainerRef}>
      <Room room={currentRoom} />
    </pixiContainer>
  )
}

// --- canvas size from room ---

function useRoomSize() {
  const room = useWorldStore(s => s.currentRoom)
  const layout = ROOMS[room]
  return { w: layout.cols * TILE, h: layout.rows * TILE }
}

// --- main export ---

export function PixiCanvas() {
  useDataLoader()

  const { w, h } = useRoomSize()

  // Start playback controller
  useEffect(() => {
    playbackController.start()
    return () => playbackController.stop()
  }, [])

  return (
    <div className="w-screen h-screen bg-[#1a1a2e] overflow-hidden relative">
      <div className="w-full h-full flex items-center justify-center">
        <Application
          width={w}
          height={h}
          background={0x1a1a2e}
          antialias={false}
          resolution={1}
        >
          <WorldScene />
        </Application>
      </div>

      {/* React UI overlays */}
      <TopBar />
      <BottomBar />
      <RoomNav />
      <SidePanel />
    </div>
  )
}
