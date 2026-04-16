import { extend } from '@pixi/react'
import { Graphics, Container } from 'pixi.js'
import { useCallback, useLayoutEffect, useRef } from 'react'
import { ROOMS, TILE } from '../../lib/roomConfig'
import type { RoomId } from '../../lib/types'
import { placeFurniture, type FurniturePlacement } from './tilesets'
import { placeAnimated, type AnimatedPlacement } from './animated'

extend({ Graphics, Container })

// --- palette (floors / walls still drawn with solid fills — LimeZu furniture sits on top) ---
const P = {
  floorA: 0xe8d5b7, floorB: 0xdfc9a6,
  wall: 0x6b5344, wallHi: 0x8b7355,
  desk: 0xb8956a, deskHi: 0xcca87a, deskEdge: 0x9a7b55,
  window: 0xb8d4e8, windowFrame: 0x8b7355,
  grass: 0x6db56d, grassB: 0x5da55d,
  bench: 0x8b7355,
  tile: 0xd4cec4, tileB: 0xcac3b8,
  track: 0xc97b5a,
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

// --- room "base" draw (floor + walls + windows — drawn with Graphics) ---
// Furniture for each room is layered on top as Sprites via FURNITURE below.

function drawClassroomBase(g: Graphics) {
  const { cols, rows } = ROOMS['教室']
  drawCheckerFloor(g, cols, rows, P.floorA, P.floorB)
  drawWalls(g, cols, rows)
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
  const w = cols * TILE
  g.rect(0, 0, w, TILE).fill(P.wall).rect(0, TILE - 4, w, 4).fill(P.wallHi)
  g.rect(0, (rows - 1) * TILE, w, TILE).fill(P.wall).rect(0, (rows - 1) * TILE, w, 4).fill(P.wallHi)

  for (let i = 2; i < cols - 2; i += 2) {
    g.rect(i * TILE + 4, TILE + 2, TILE - 8, TILE * 1.5).fill(0x5a7b8f)
    g.rect(i * TILE + 6, TILE + 4, TILE - 12, TILE * 1.5 - 4).fill(0x6a8b9f)
    g.rect(i * TILE + TILE / 2 + 4, TILE + TILE * 0.8, 3, 6).fill(0x888888)
  }

  const nbx = 12 * TILE
  g.rect(nbx, TILE + 2, 4 * TILE, 2.5 * TILE).fill(0x8b6e4e)
  g.rect(nbx + 4, TILE + 6, 4 * TILE - 8, 2.5 * TILE - 8).fill(0xd4c4a8)

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
}

function drawDorm(g: Graphics) {
  const { cols, rows } = ROOMS['宿舍']
  drawCheckerFloor(g, cols, rows, P.floorA, P.floorB)
  drawWalls(g, cols, rows)
  // Desk area table (beds + wardrobe rendered as sprites via FURNITURE)
  drawTable(g, 10, 10, 4, 1.5)
  const wy = 6 * TILE
  g.rect(-2, wy, TILE + 2, TILE * 2 + 4).fill(P.windowFrame)
  g.rect(2, wy + 2, TILE - 6, TILE * 2).fill(P.window)
  g.rect(2, wy + TILE - 1, TILE - 6, 3).fill(P.windowFrame)
}

function drawPlayground(g: Graphics) {
  const { cols, rows } = ROOMS['操场']
  const w = cols * TILE, h = rows * TILE

  // Solid grass base — no checkerboard pattern for outdoor areas
  g.rect(0, 0, w, h).fill(P.grass)
  // Subtle darker grass patches for visual texture
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++)
      if ((r * 7 + c * 13 + 3) % 6 < 2)
        g.rect(c * TILE, r * TILE, TILE, TILE).fill(P.grassB)

  // Track (runs full width of field, below court area)
  g.rect(2 * TILE, 16 * TILE, 26 * TILE, TILE * 2).fill(P.track)
  g.rect(2 * TILE, 16 * TILE + 2, 26 * TILE, 3).fill(0xffffff)
  g.rect(2 * TILE, 17 * TILE, 26 * TILE, 3).fill(0xffffff)

  // Benches alongside the court
  for (const bx of [3, 25]) {
    g.rect(bx * TILE - TILE, 14 * TILE, TILE * 2.5, TILE * 0.6).fill(P.bench)
    g.rect(bx * TILE - TILE + 4, 14 * TILE + 2, TILE * 2.5 - 8, 2).fill(P.deskHi)
  }
}

function drawLibrary(g: Graphics) {
  const { cols, rows } = ROOMS['图书馆']
  drawCheckerFloor(g, cols, rows, P.floorA, P.floorB)
  drawWalls(g, cols, rows)
  // Bookshelves + reading tables rendered as sprites via FURNITURE
  for (const wy of [4, 9, 14]) {
    g.rect(-2, wy * TILE, TILE + 2, TILE * 1.6 + 4).fill(P.windowFrame)
    g.rect(2, wy * TILE + 2, TILE - 6, TILE * 1.6).fill(P.window)
  }
}

function drawConvenienceStore(g: Graphics) {
  const { cols, rows } = ROOMS['小卖部']
  drawCheckerFloor(g, cols, rows, P.tile, P.tileB)
  drawWalls(g, cols, rows)
  // Shelves, vending machines, cooler rendered as sprites via FURNITURE
}

// --- dispatch ---

const BASE_DRAW_FN: Record<RoomId, (g: Graphics) => void> = {
  '教室': drawClassroomBase,
  '走廊': drawHallway,
  '食堂': drawCafeteria,
  '宿舍': drawDorm,
  '操场': drawPlayground,
  '图书馆': drawLibrary,
  '小卖部': drawConvenienceStore,
}

/** Furniture sprites to lay over the base graphics for each room.
 * Coords are top-left tile positions (col, row). Sprite dimensions come
 * from the manifest / the actual PNGs.
 *
 * Alignment convention for classroom desks:
 *   Seats in roomConfig.ts sit at cx=[3.5, 7.5, ...], ry=[6, 9, ...].
 *   A 1×2-tile desk centered on the character tile has its top-left at
 *   (floor(cx) - 0 = 3, 7, 11, 15, 19) and (ry - 1 = 5, 8, 11, 14). That
 *   lands the character sprite visually on top of the desk.
 */
const FURNITURE: Partial<Record<RoomId, FurniturePlacement[]>> = {
  '教室': (() => {
    const items: FurniturePlacement[] = []
    // Blackboard anchored at top-center (above teacher zone)
    items.push({ cat: 'classroom', name: 'chalkboard_black', col: 11, row: 0 })
    // Posters flanking the board
    items.push({ cat: 'classroom', name: 'poster_numbers', col: 7, row: 0 })
    items.push({ cat: 'classroom', name: 'poster_abc', col: 15, row: 0 })
    // Teacher desk (4×2) centered around column 12
    items.push({ cat: 'classroom', name: 'teacher_desk', col: 10, row: 3 })
    // Student desks — 5 cols × 4 rows, aligned so character overlaps desk
    const cols = [3, 7, 11, 15, 19]
    const rows = [5, 8, 11, 14]
    for (const r of rows) for (const c of cols) {
      items.push({ cat: 'classroom', name: 'student_desk', col: c, row: r })
    }
    // Notice board on a clear wall strip (left wall between windows)
    items.push({ cat: 'classroom', name: 'notice_board', col: 1, row: 16 })
    return items
  })(),
  '操场': [
    { cat: 'sports', name: 'basketball_court', col: 9, row: 3 },
  ],
  '图书馆': (() => {
    const items: FurniturePlacement[] = []
    // Tall bookshelves along right wall (col 21, each 2×3)
    for (const r of [2, 5, 8, 11, 14])
      items.push({ cat: 'library', name: 'bookshelf_tall_a', col: 21, row: r })
    // Reading tables near the 4 table zones
    items.push({ cat: 'library', name: 'reading_table', col: 4, row: 5 })
    items.push({ cat: 'library', name: 'reading_table', col: 12, row: 5 })
    items.push({ cat: 'library', name: 'reading_table', col: 4, row: 11 })
    items.push({ cat: 'library', name: 'reading_table', col: 12, row: 11 })
    // Short bookshelves as room dividers
    items.push({ cat: 'library', name: 'bookshelf_colorful', col: 19, row: 3 })
    items.push({ cat: 'library', name: 'bookshelf_short', col: 19, row: 7 })
    return items
  })(),
  '宿舍': [
    // Beds near the 3 bed zones (bed_1@3,4  bed_2@10,4  bed_3@17,4)
    { cat: 'dorm', name: 'bed_green', col: 2, row: 2 },
    { cat: 'dorm', name: 'bed_blue', col: 9, row: 2 },
    { cat: 'dorm', name: 'bed_pink', col: 16, row: 2 },
    // Wardrobe against right wall
    { cat: 'dorm', name: 'wardrobe', col: 21, row: 2 },
  ],
  '食堂': [
    // Kitchen equipment behind the counter strip (top of room)
    { cat: 'cafeteria', name: 'fridge', col: 1, row: 1 },
    { cat: 'cafeteria', name: 'stove', col: 25, row: 1 },
    { cat: 'cafeteria', name: 'counter_long', col: 6, row: 1 },
    // Dining tables in the eating area
    { cat: 'cafeteria', name: 'dining_table', col: 8, row: 7 },
    { cat: 'cafeteria', name: 'dining_table', col: 18, row: 7 },
  ],
  '小卖部': [
    // Vending machines against top wall
    { cat: 'store', name: 'vending_a', col: 1, row: 1 },
    { cat: 'store', name: 'vending_b', col: 13, row: 1 },
    // Tall shelf and cooler flanking the aisles
    { cat: 'store', name: 'shelf_tall', col: 2, row: 5 },
    { cat: 'store', name: 'cooler_glass', col: 12, row: 5 },
    // Cash register near counter zone
    { cat: 'store', name: 'register', col: 7, row: 3 },
  ],
}

/** Animated objects per room. Pixi plays the sheet as a frame strip.
 * Coords are top-left tile positions. */
const ANIMATED: Partial<Record<RoomId, AnimatedPlacement[]>> = {
  // Pendulum clock on back wall, right of posters (1×3 tiles)
  '教室': [{ name: 'pendulum_clock', col: 22, row: 0 }],
  // Fridge in the kitchen strip at top-left (1×3 tiles)
  '食堂': [{ name: 'fridge_cake', col: 2, row: 1 }],
  // Old TV on back wall, centered-ish (2×2 tiles)
  '宿舍': [{ name: 'old_tv', col: 11, row: 1 }],
}

interface RoomProps {
  room: RoomId
}

export function Room({ room }: RoomProps) {
  const draw = useCallback(
    (g: Graphics) => {
      g.clear()
      BASE_DRAW_FN[room]?.(g)
    },
    [room],
  )

  // One container per Room mount; cleared on room change so stale furniture
  // from a previous room doesn't pile up on top of the new base.
  const furnitureRef = useRef<Container | null>(null)

  const furnitureContainerRef = useCallback((node: Container | null) => {
    furnitureRef.current = node
  }, [])

  useLayoutEffect(() => {
    const c = furnitureRef.current
    if (!c) return
    // Clear any previous furniture synchronously before paint so stale
    // sprites from the old room never appear on the new room's floor.
    for (const child of [...c.children]) child.destroy({ children: true })
    const items = FURNITURE[room]
    if (items) placeFurniture(c, items)
    const anims = ANIMATED[room]
    if (anims) placeAnimated(c, anims)
  }, [room])

  return (
    <pixiContainer>
      <pixiGraphics draw={draw} />
      <pixiContainer ref={furnitureContainerRef} />
    </pixiContainer>
  )
}
