import { AnimatedSprite, Assets, Container, Rectangle, Texture } from 'pixi.js'
import { TILE } from '../../lib/roomConfig'
import type { AnimatedManifest } from '../../lib/data'

let cachedManifest: AnimatedManifest | null = null

export function getAnimatedManifest(): AnimatedManifest | null {
  return cachedManifest
}

/** Preload every animated sheet in the manifest. Caches the manifest so
 * placement code can look up frame dimensions without an extra fetch. */
export async function preloadAnimated(manifest: AnimatedManifest): Promise<void> {
  cachedManifest = manifest
  const urls = Object.keys(manifest).map(n => `/data/animated/${n}.png`)
  await Promise.all(
    urls.map(async url => {
      try {
        const tex = await Assets.load(url)
        if (tex?.source) tex.source.scaleMode = 'nearest'
      } catch {
        // non-fatal
      }
    }),
  )
}

export interface AnimatedPlacement {
  /** Sprite name (matches manifest key) */
  name: string
  /** Tile X (top-left, in tile units) */
  col: number
  /** Tile Y (top-left, in tile units) */
  row: number
}

function buildFrames(
  baseTex: Texture,
  frameW: number,
  frameH: number,
  count: number,
): Texture[] {
  const frames: Texture[] = []
  for (let i = 0; i < count; i++) {
    frames.push(
      new Texture({
        source: baseTex.source,
        frame: new Rectangle(i * frameW, 0, frameW, frameH),
      }),
    )
  }
  return frames
}

/** Place animated sprites onto a container. Frames are sliced from each
 * sheet on resolve; Pixi's AnimatedSprite handles playback. */
export function placeAnimated(
  parent: Container,
  items: AnimatedPlacement[],
): void {
  const manifest = cachedManifest
  if (!manifest) return
  for (const { name, col, row } of items) {
    const spec = manifest[name]
    if (!spec) continue
    const holder = new Container()
    holder.x = col * TILE
    holder.y = row * TILE
    parent.addChild(holder)
    Assets.load(`/data/animated/${name}.png`)
      .then((tex: Texture) => {
        if (tex?.source) tex.source.scaleMode = 'nearest'
        const frames = buildFrames(tex, spec.frame_w, spec.frame_h, spec.count)
        const anim = new AnimatedSprite(frames)
        anim.animationSpeed = spec.fps / 60
        anim.play()
        holder.addChild(anim)
      })
      .catch(() => {})
  }
}
