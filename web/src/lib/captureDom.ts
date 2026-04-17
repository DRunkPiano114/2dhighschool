/**
 * Screenshot a DOM subtree to a PNG Blob. Shared by the three share cards
 * (daily / scene / agent) — all of them capture an off-screen rendered node.
 *
 * - Awaits `document.fonts.ready` so CJK glyphs don't fall through to the
 *   default font mid-capture.
 * - Awaits `img.load` on every `<img>` in the tree so sprite portraits don't
 *   land as broken-image placeholders.
 * - `skipFonts: true` deliberately avoids inlining the Google Fonts WOFF2
 *   subsets into the SVG snapshot (~10s for negligible visual benefit).
 *   Chinese glyphs in the resulting PNG render via the OS fallback family
 *   (PingFang on macOS, YaHei on Windows). The on-page preview still uses
 *   the webfonts.
 * - `filter` honours `data-exclude-from-capture` so callers can hide nav
 *   chrome and the share dock itself when the entire page IS the target.
 */
export async function captureDomBlob(node: HTMLElement): Promise<Blob | null> {
  if (document.fonts?.ready) {
    try {
      await document.fonts.ready
    } catch {
      // ignore — font loading failure shouldn't block capture
    }
  }
  const imgs = Array.from(node.querySelectorAll('img'))
  await Promise.all(
    imgs.map(img => {
      if (img.complete && img.naturalWidth > 0) return Promise.resolve()
      return new Promise<void>(resolve => {
        img.addEventListener('load', () => resolve(), { once: true })
        img.addEventListener('error', () => resolve(), { once: true })
      })
    }),
  )
  // Dynamic import keeps html-to-image (~100KB) out of the main bundle.
  const { toBlob } = await import('html-to-image')
  return toBlob(node, {
    pixelRatio: 2,
    backgroundColor: '#f5efe0',
    skipFonts: true,
    filter: el => !(el instanceof HTMLElement && el.dataset.excludeFromCapture !== undefined),
  })
}
