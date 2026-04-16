import { Assets, Sprite, Texture, Container } from 'pixi.js'
import { TILE } from '../../lib/roomConfig'
import type { TilesetManifest } from '../../lib/data'

/** Preload every furniture sprite in the manifest so Sprite.from hits cache. */
export async function preloadTilesets(manifest: TilesetManifest): Promise<void> {
  const urls: string[] = []
  for (const [cat, items] of Object.entries(manifest)) {
    for (const name of Object.keys(items)) {
      urls.push(`/data/tilesets/${cat}/${name}.png`)
    }
  }
  await Promise.all(
    urls.map(async url => {
      try {
        const tex = await Assets.load(url)
        if (tex?.source) tex.source.scaleMode = 'nearest'
      } catch {
        // Non-fatal — missing sprite just won't render.
      }
    }),
  )
}

export interface FurniturePlacement {
  /** Tileset category, e.g. 'classroom' */
  cat: string
  /** Sprite name within category */
  name: string
  /** Tile X (top-left of sprite, in tile units) */
  col: number
  /** Tile Y (top-left of sprite, in tile units) */
  row: number
  /** Uniform scale factor (default 1). Use for oversized elements like courts. */
  scale?: number
}

/** Place a list of furniture sprites into a Pixi Container at tile coords.
 * Safe to call even if the tileset preload hasn't resolved yet — each sprite
 * starts empty and swaps to the real texture on resolve. */
export function placeFurniture(
  parent: Container,
  items: FurniturePlacement[],
): void {
  for (const { cat, name, col, row, scale } of items) {
    const sprite = new Sprite(Texture.EMPTY)
    sprite.x = col * TILE
    sprite.y = row * TILE
    if (scale && scale !== 1) sprite.scale.set(scale)
    parent.addChild(sprite)
    Assets.load(`/data/tilesets/${cat}/${name}.png`)
      .then((tex: Texture) => {
        if (tex?.source) tex.source.scaleMode = 'nearest'
        sprite.texture = tex
      })
      .catch(() => {
        // Leave as empty sprite — still valid, just invisible.
      })
  }
}
