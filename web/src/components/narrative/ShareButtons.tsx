import { useState } from 'react'

interface ShareCardMeta {
  caption: string
  hashtags: string[]
  filename: string
}

export interface ShareButtonsProps {
  /** Human label for the card type, used in tooltips and toasts. */
  cardLabel?: string
  /** Returns the PNG Blob. Caller owns where the pixels come from — typically
   * an off-screen render captured via useShareCapture + html-to-image. */
  capture: () => Promise<Blob | null>
  /** Caption / hashtags / filename payload, pre-computed in Python during
   * export. `null` hides copy-caption UX; `available=false` hides the dock
   * entirely. */
  meta: ShareCardMeta | null
  /** Whether to render the "复制文案" button. Daily report hides it because
   * the on-page body *is* the caption. */
  showCopy?: boolean
  /** When false, the dock doesn't render at all (e.g. scene is all-solo,
   * data still loading). */
  available?: boolean
}

/**
 * Pure-UI save/share dock. All three share cards (daily / scene / agent)
 * share this component — each caller wires in their own capture function
 * and meta payload. No /api probing, no URL building.
 */
export function ShareButtons({
  cardLabel = '分享卡',
  capture,
  meta,
  showCopy = true,
  available = true,
}: ShareButtonsProps) {
  const [toast, setToast] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [copying, setCopying] = useState(false)

  if (!available) return null

  const flashToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2200)
  }

  async function saveCard() {
    if (saving) return
    setSaving(true)
    try {
      let blob: Blob | null = null
      try {
        blob = await capture()
      } catch (err) {
        console.error('share capture failed', err)
        flashToast('截图失败')
        return
      }
      if (!blob) {
        flashToast('截图失败')
        return
      }
      const filename = meta?.filename ?? 'simcampus_card.png'

      // Progressive: Web Share API first (mobile native share sheet), then
      // download fallback (desktop). Image-only — captions belong to the
      // copy button; bundling them here makes the two actions feel identical
      // on platforms that merge share-sheet text with the attached file.
      const file = new File([blob], filename, { type: 'image/png' })
      if (typeof navigator.canShare === 'function' && navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file] })
          return
        } catch (err) {
          if (!(err instanceof DOMException) || err.name !== 'AbortError') {
            console.error('share failed, falling back to download', err)
          } else {
            return
          }
        }
      }

      const url = URL.createObjectURL(blob)
      const a = Object.assign(document.createElement('a'), { href: url, download: filename })
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      flashToast(`${cardLabel}已保存`)
    } finally {
      setSaving(false)
    }
  }

  async function copyCaption() {
    if (copying || !meta) return
    setCopying(true)
    try {
      const text = `${meta.caption}\n\n${meta.hashtags.join(' ')}`
      await navigator.clipboard.writeText(text)
      flashToast('文案已复制')
    } catch {
      flashToast('复制失败')
    } finally {
      setCopying(false)
    }
  }

  const copyDisabled = !meta

  return (
    <div className="share-dock">
      <div className="share-dock-label" aria-hidden>✂️ 把这一刻分享出去</div>
      <div className="share-buttons" role="group" aria-label="分享操作">
        <button
          type="button"
          className={`share-btn share-btn--primary${saving ? ' share-btn-busy' : ''}`}
          onClick={saveCard}
          disabled={saving}
          title={saving ? '保存中…' : '保存图'}
        >
          <span className="share-btn-icon">📥</span>
          <span className="share-btn-label">{saving ? '保存中…' : '保存图'}</span>
        </button>
        {showCopy && (
          <button
            type="button"
            className={`share-btn share-btn--secondary${copying ? ' share-btn-busy' : ''}`}
            onClick={copyCaption}
            disabled={copyDisabled || copying}
            title={copyDisabled ? '文案尚未就绪' : copying ? '复制中…' : '复制文案'}
          >
            <span className="share-btn-icon">📋</span>
            <span className="share-btn-label">{copying ? '复制中…' : '复制文案'}</span>
          </button>
        )}
        {toast && <div className="share-toast" role="status">{toast}</div>}
      </div>
    </div>
  )
}
