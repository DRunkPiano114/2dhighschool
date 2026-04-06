import { extend } from '@pixi/react'
import { Graphics } from 'pixi.js'
import { useCallback } from 'react'
import { ROOMS, TILE } from '../../lib/roomConfig'
import type { RoomId } from '../../lib/types'

extend({ Graphics })

// --- palette ---
const P = {
  floorA: 0xe8d5b7, floorB: 0xdfc9a6,
  wall: 0x6b5344, wallHi: 0x8b7355,
  board: 0x2d5a3d, boardFrame: 0x5c4033, boardChalk: 0x4a7d5e,
  desk: 0xb8956a, deskHi: 0xcca87a, deskEdge: 0x9a7b55,
  chair: 0x7a6840,
  teachDesk: 0x8b6e4e, teachHi: 0xa0845c, teachEdge: 0x6b4e2e,
  window: 0xb8d4e8, windowFrame: 0x8b7355,
  grass: 0x6db56d, grassB: 0x5da55d,
  court: 0xd4a053, courtLine: 0xffffff,
  bench: 0x8b7355,
  shelf: 0xa0845c, shelfHi: 0xb8956a,
  counter: 0xc9b896,
  bed: 0x7b8fa8, bedFrame: 0x6b5344,
  tile: 0xd4cec4, tileB: 0xcac3b8,
  track: 0xc97b5a,
  bookshelf: 0x6b4e2e,
}

// --- shared draw helpers ---

function drawCheckerFloor(g: Graphics, cols: number, rows: number, a: number, b: number) {
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++)
      g.rect(c * TILE, r * TILE, TILE, TILE).fill((r + c) % 2 === 0 ? a : b)
}

function drawWalls(g: Graphics, cols: number, rows: number) {
  const w = cols * TILE, h = rows * TILE
  g.rect(0, 0, w, TILE).fill(P.wall).rect(0, TILE - 4, w, 4).fill(P.wallHi)
  g.rect(0, (rows - 1) * TILE, w, TILE).fill(P.wall).rect(0, (rows - 1) * TILE, w, 4).fill(P.wallHi)
  g.rect(0, 0, TILE, h).fill(P.wall).rect(TILE - 4, 0, 4, h).fill(P.wallHi)
  g.rect((cols - 1) * TILE, 0, TILE, h).fill(P.wall).rect((cols - 1) * TILE, 0, 4, h).fill(P.wallHi)
}

function drawTable(g: Graphics, cx: number, cy: number, tw = 3, th = 2) {
  const x = cx * TILE - (tw * TILE) / 2
  const y = cy * TILE - (th * TILE) / 2
  g.rect(x, y + th * TILE, tw * TILE, 4).fill(P.deskEdge)
  g.rect(x, y, tw * TILE, th * TILE).fill(P.desk)
  g.rect(x + 2, y + 2, tw * TILE - 4, 3).fill(P.deskHi)
}

// --- room draw functions ---

function drawClassroom(g: Graphics) {
  const { cols, rows } = ROOMS['教室']
  drawCheckerFloor(g, cols, rows, P.floorA, P.floorB)
  drawWalls(g, cols, rows)

  // Blackboard
  const bx = 4 * TILE, bw = 16 * TILE
  g.rect(bx - 6, TILE * 0.25 - 4, bw + 12, TILE * 1.5 + 8).fill(P.boardFrame)
  g.rect(bx, TILE * 0.25, bw, TILE * 1.5).fill(P.board)
  g.rect(bx + 8, TILE * 1.5 - 2, bw - 16, 6).fill(P.boardChalk)

  // Teacher desk
  const tdx = 9 * TILE, tdw = 6 * TILE, tdh = 1.4 * TILE
  g.rect(tdx, 3 * TILE + tdh, tdw, 5).fill(P.teachEdge)
  g.rect(tdx, 3 * TILE, tdw, tdh).fill(P.teachDesk)
  g.rect(tdx + 2, 3 * TILE + 2, tdw - 4, 3).fill(P.teachHi)

  // Student desks 5×4
  const cx = [3.5, 7.5, 11.5, 15.5, 19.5]
  const ry = [6, 9, 12, 15]
  const dw = TILE * 1.4, dh = TILE * 0.75
  for (const r of ry) for (const c of cx) {
    const dx = c * TILE - dw / 2, dy = r * TILE
    g.rect(dx, dy + dh, dw, 4).fill(P.deskEdge)
    g.rect(dx, dy, dw, dh).fill(P.desk)
    g.rect(dx + 2, dy + 2, dw - 4, 2).fill(P.deskHi)
    g.rect(c * TILE - TILE * 0.3, dy + dh + 10, TILE * 0.6, TILE * 0.45).fill(P.chair)
  }

  // Windows on left wall
  for (const wy of [4, 8, 12]) {
    const ww = TILE - 8, wh = TILE * 1.4, py = wy * TILE
    g.rect(0, py - 2, ww + 4, wh + 4).fill(P.windowFrame)
    g.rect(2, py, ww, wh).fill(P.window)
    g.rect(2, py + wh / 2 - 1, ww, 3).fill(P.windowFrame)
    g.rect(2 + ww / 2 - 1, py, 3, wh).fill(P.windowFrame)
  }
}

function drawHallway(g: Graphics) {
  const { cols, rows } = ROOMS['走廊']
  drawCheckerFloor(g, cols, rows, P.tile, P.tileB)
  // Top/bottom walls
  const w = cols * TILE
  g.rect(0, 0, w, TILE).fill(P.wall).rect(0, TILE - 4, w, 4).fill(P.wallHi)
  g.rect(0, (rows - 1) * TILE, w, TILE).fill(P.wall).rect(0, (rows - 1) * TILE, w, 4).fill(P.wallHi)

  // Lockers on top wall
  for (let i = 2; i < cols - 2; i += 2) {
    g.rect(i * TILE + 4, TILE + 2, TILE - 8, TILE * 1.5).fill(0x5a7b8f)
    g.rect(i * TILE + 6, TILE + 4, TILE - 12, TILE * 1.5 - 4).fill(0x6a8b9f)
    g.rect(i * TILE + TILE / 2 + 4, TILE + TILE * 0.8, 3, 6).fill(0x888888)
  }

  // Notice board
  const nbx = 12 * TILE
  g.rect(nbx, TILE + 2, 4 * TILE, 2.5 * TILE).fill(0x8b6e4e)
  g.rect(nbx + 4, TILE + 6, 4 * TILE - 8, 2.5 * TILE - 8).fill(0xd4c4a8)

  // Windows on bottom wall
  for (const wx of [4, 10, 16, 22]) {
    const py = (rows - 1) * TILE
    g.rect(wx * TILE - 2, py - TILE * 0.3, TILE + 4, TILE * 0.3 + 4).fill(P.windowFrame)
    g.rect(wx * TILE, py - TILE * 0.3 + 2, TILE, TILE * 0.3 - 2).fill(P.window)
  }
}

function drawCafeteria(g: Graphics) {
  const { cols, rows } = ROOMS['食堂']
  drawCheckerFloor(g, cols, rows, P.tile, P.tileB)
  drawWalls(g, cols, rows)

  // Food counter along top wall
  g.rect(3 * TILE, TILE + 4, 22 * TILE, TILE * 1.5).fill(P.counter)
  g.rect(3 * TILE + 4, TILE + 8, 22 * TILE - 8, 3).fill(0xddd5c5)

  // Tables (6 tables, 3×2 grid)
  for (const z of ROOMS['食堂'].zones) drawTable(g, z.x, z.y)
}

function drawDorm(g: Graphics) {
  const { cols, rows } = ROOMS['宿舍']
  drawCheckerFloor(g, cols, rows, P.floorA, P.floorB)
  drawWalls(g, cols, rows)

  // Bunk beds
  for (const z of ROOMS['宿舍'].zones.filter(z => z.id.startsWith('bed'))) {
    const bx = z.x * TILE - TILE * 1.5
    const by = z.y * TILE - TILE
    g.rect(bx, by, TILE * 3, TILE * 2).fill(P.bedFrame)
    g.rect(bx + 3, by + 3, TILE * 3 - 6, TILE * 2 - 6).fill(P.bed)
    // Pillow
    g.rect(bx + 6, by + 6, TILE - 4, TILE * 0.6).fill(0xeee8dc)
  }

  // Desk area
  drawTable(g, 10, 10, 4, 1.5)

  // Window
  const wy = 6 * TILE
  g.rect(-2, wy, TILE + 2, TILE * 2 + 4).fill(P.windowFrame)
  g.rect(2, wy + 2, TILE - 6, TILE * 2).fill(P.window)
  g.rect(2, wy + TILE - 1, TILE - 6, 3).fill(P.windowFrame)
}

function drawPlayground(g: Graphics) {
  const { cols, rows } = ROOMS['操场']
  // Grass
  drawCheckerFloor(g, cols, rows, P.grass, P.grassB)

  // Basketball court (center)
  const cx = 15 * TILE, cy = 8 * TILE
  g.rect(cx - 5 * TILE, cy - 3 * TILE, 10 * TILE, 6 * TILE).fill(P.court)
  // Court lines
  g.rect(cx - 5 * TILE, cy - 3 * TILE, 10 * TILE, 3).fill(P.courtLine)
  g.rect(cx - 5 * TILE, cy + 3 * TILE - 3, 10 * TILE, 3).fill(P.courtLine)
  g.rect(cx - 5 * TILE, cy - 3 * TILE, 3, 6 * TILE).fill(P.courtLine)
  g.rect(cx + 5 * TILE - 3, cy - 3 * TILE, 3, 6 * TILE).fill(P.courtLine)
  // Center line
  g.rect(cx - 5 * TILE, cy - 1, 10 * TILE, 3).fill(P.courtLine)
  // Center circle (approximation)
  g.rect(cx - TILE, cy - TILE, TILE * 2, TILE * 2).fill(P.court)

  // Benches
  for (const bx of [3, 25]) {
    g.rect(bx * TILE - TILE, 14 * TILE, TILE * 2.5, TILE * 0.6).fill(P.bench)
    g.rect(bx * TILE - TILE + 4, 14 * TILE + 2, TILE * 2.5 - 8, 2).fill(P.deskHi)
  }

  // Track stripe at bottom
  g.rect(2 * TILE, 16 * TILE, 26 * TILE, TILE * 2).fill(P.track)
  g.rect(2 * TILE, 16 * TILE + 2, 26 * TILE, 3).fill(0xffffff)
  g.rect(2 * TILE, 17 * TILE, 26 * TILE, 3).fill(0xffffff)
}

function drawLibrary(g: Graphics) {
  const { cols, rows } = ROOMS['图书馆']
  drawCheckerFloor(g, cols, rows, P.floorA, P.floorB)
  drawWalls(g, cols, rows)

  // Bookshelves along right wall
  for (let r = 2; r < rows - 2; r += 2) {
    g.rect((cols - 2) * TILE, r * TILE, TILE, TILE * 1.5).fill(P.bookshelf)
    g.rect((cols - 2) * TILE + 3, r * TILE + 3, TILE - 6, TILE * 0.4).fill(0xc4524a)
    g.rect((cols - 2) * TILE + 3, r * TILE + TILE * 0.5, TILE - 6, TILE * 0.4).fill(0x4a7bc4)
    g.rect((cols - 2) * TILE + 3, r * TILE + TILE, TILE - 6, TILE * 0.4).fill(0x5baa5b)
  }

  // Reading tables
  for (const z of ROOMS['图书馆'].zones.filter(z => z.id.startsWith('table')))
    drawTable(g, z.x, z.y, 2.5, 1.5)

  // Windows on left wall
  for (const wy of [4, 9, 14]) {
    g.rect(-2, wy * TILE, TILE + 2, TILE * 1.6 + 4).fill(P.windowFrame)
    g.rect(2, wy * TILE + 2, TILE - 6, TILE * 1.6).fill(P.window)
  }
}

function drawConvenienceStore(g: Graphics) {
  const { cols, rows } = ROOMS['小卖部']
  drawCheckerFloor(g, cols, rows, P.tile, P.tileB)
  drawWalls(g, cols, rows)

  // Counter across top
  g.rect(3 * TILE, TILE + 2, 10 * TILE, TILE * 1.3).fill(P.counter)
  g.rect(3 * TILE + 4, TILE + 6, 10 * TILE - 8, 3).fill(0xddd5c5)
  // Cash register
  g.rect(8 * TILE, TILE + 6, TILE * 0.8, TILE * 0.6).fill(0x555555)

  // Shelves
  for (let r = 5; r <= 9; r += 2) {
    g.rect(2 * TILE, r * TILE, 5 * TILE, TILE * 0.8).fill(P.shelf)
    g.rect(2 * TILE + 2, r * TILE + 2, 5 * TILE - 4, 2).fill(P.shelfHi)
    g.rect(9 * TILE, r * TILE, 5 * TILE, TILE * 0.8).fill(P.shelf)
    g.rect(9 * TILE + 2, r * TILE + 2, 5 * TILE - 4, 2).fill(P.shelfHi)
  }
}

// --- dispatch ---

const DRAW_FN: Record<RoomId, (g: Graphics) => void> = {
  '教室': drawClassroom,
  '走廊': drawHallway,
  '食堂': drawCafeteria,
  '宿舍': drawDorm,
  '操场': drawPlayground,
  '图书馆': drawLibrary,
  '小卖部': drawConvenienceStore,
}

interface RoomProps {
  room: RoomId
}

export function Room({ room }: RoomProps) {
  const draw = useCallback(
    (g: Graphics) => {
      g.clear()
      DRAW_FN[room]?.(g)
    },
    [room],
  )

  return <pixiGraphics draw={draw} />
}
