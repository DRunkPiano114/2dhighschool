/**
 * DanmuLayer: floating text overlay for broadcast mode.
 * Text scrolls right-to-left across the top of the viewport.
 */
export class DanmuLayer {
  private container: HTMLDivElement
  private items: HTMLDivElement[] = []

  constructor(parentEl: HTMLElement) {
    this.container = document.createElement('div')
    Object.assign(this.container.style, {
      position: 'absolute',
      top: '0',
      left: '0',
      right: '0',
      height: '80px',
      overflow: 'hidden',
      pointerEvents: 'none',
      zIndex: '20',
    })
    parentEl.appendChild(this.container)
  }

  /** Fire danmu texts (up to 2 per tick). */
  fire(texts: string[]) {
    for (let i = 0; i < texts.length; i++) {
      const el = document.createElement('div')
      el.textContent = texts[i]
      Object.assign(el.style, {
        position: 'absolute',
        right: '-300px',
        top: `${12 + i * 28}px`,
        whiteSpace: 'nowrap',
        fontSize: '15px',
        fontFamily: '"Noto Sans SC", sans-serif',
        fontWeight: '500',
        color: 'rgba(255,255,255,0.85)',
        textShadow: '1px 1px 3px rgba(0,0,0,0.6)',
        transition: 'none',
        willChange: 'transform',
      })
      this.container.appendChild(el)
      this.items.push(el)

      // Animate
      const width = this.container.offsetWidth + 300
      el.animate(
        [
          { transform: 'translateX(0)' },
          { transform: `translateX(-${width + 300}px)` },
        ],
        { duration: 8000, easing: 'linear', fill: 'forwards' },
      ).onfinish = () => {
        el.remove()
        const idx = this.items.indexOf(el)
        if (idx >= 0) this.items.splice(idx, 1)
      }
    }
  }

  clear() {
    for (const el of this.items) el.remove()
    this.items = []
  }

  destroy() {
    this.clear()
    this.container.remove()
  }
}
