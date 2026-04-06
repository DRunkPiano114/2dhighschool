import { Container } from 'pixi.js'

export interface BubbleData {
  agentId: string
  displayName: string
  text: string
  type: 'speech' | 'thought' | 'whisper_notice'
  target?: string
}

/**
 * BubbleOverlay: imperative DOM overlay, synced with PixiJS Ticker.
 * Positions HTML bubbles above character sprites using world→screen projection.
 */
export class BubbleOverlay {
  private container: HTMLDivElement
  private elements = new Map<string, HTMLDivElement>()

  constructor(parentEl: HTMLElement) {
    this.container = document.createElement('div')
    this.container.className = 'bubble-overlay'
    Object.assign(this.container.style, {
      position: 'absolute',
      inset: '0',
      pointerEvents: 'none',
      overflow: 'hidden',
    })
    parentEl.appendChild(this.container)
  }

  /** Set which bubbles to show. Call when tick changes. */
  setBubbles(bubbles: BubbleData[]) {
    // Remove stale
    const activeIds = new Set(bubbles.map(b => b.agentId))
    for (const [id, el] of this.elements) {
      if (!activeIds.has(id)) {
        el.remove()
        this.elements.delete(id)
      }
    }

    // Create or update
    for (const b of bubbles) {
      let el = this.elements.get(b.agentId)
      if (!el) {
        el = this.createBubbleEl(b)
        this.container.appendChild(el)
        this.elements.set(b.agentId, el)
      }
      this.updateBubbleContent(el, b)
    }
  }

  /**
   * Update positions. Called from PixiJS Ticker (same rAF frame as render).
   * Projects character world positions to screen coordinates.
   */
  updatePositions(
    sprites: Map<string, Container>,
    worldContainer: Container,
  ) {
    for (const [agentId, el] of this.elements) {
      const sprite = sprites.get(agentId)
      if (!sprite) {
        el.style.display = 'none'
        continue
      }

      const parent = worldContainer.parent
      if (!parent) { el.style.display = 'none'; continue }
      const global = sprite.toGlobal(parent)
      const x = global.x
      const y = global.y - 50 // offset above character

      el.style.display = ''
      el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`
    }
  }

  clear() {
    for (const el of this.elements.values()) el.remove()
    this.elements.clear()
  }

  destroy() {
    this.clear()
    this.container.remove()
  }

  private createBubbleEl(b: BubbleData): HTMLDivElement {
    const el = document.createElement('div')
    el.className = `bubble bubble-${b.type}`
    Object.assign(el.style, {
      position: 'absolute',
      left: '0',
      top: '0',
      maxWidth: '200px',
      padding: '6px 10px',
      borderRadius: '8px',
      fontSize: '13px',
      lineHeight: '1.4',
      fontFamily: b.type === 'thought'
        ? '"LXGW WenKai", serif'
        : '"Noto Sans SC", sans-serif',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-all',
      pointerEvents: 'auto',
      cursor: 'pointer',
      transition: 'opacity 0.3s, transform 0.3s',
      willChange: 'transform',
    })
    return el
  }

  private updateBubbleContent(el: HTMLDivElement, b: BubbleData) {
    const isThought = b.type === 'thought'
    const isWhisper = b.type === 'whisper_notice'

    Object.assign(el.style, {
      background: isThought
        ? 'rgba(233,69,96,0.12)'
        : isWhisper
          ? 'rgba(180,180,200,0.15)'
          : '#faf3e0',
      border: isThought
        ? '1.5px dashed rgba(233,69,96,0.4)'
        : isWhisper
          ? '1px dashed #aaa'
          : '1.5px solid #e0d5c0',
      fontStyle: isThought ? 'italic' : 'normal',
      color: isThought ? '#c0475a' : isWhisper ? '#888' : '#2c2c2c',
    })

    // Truncate to 2 lines worth (~40 chars)
    const truncated = b.text.length > 40 ? b.text.slice(0, 39) + '…' : b.text
    const nameHtml = `<span style="font-weight:600;font-size:11px;opacity:0.7">${b.displayName}</span><br/>`

    el.innerHTML = isWhisper
      ? `<span style="font-size:12px;color:#888">${truncated}</span>`
      : `${nameHtml}${truncated}`
  }
}
