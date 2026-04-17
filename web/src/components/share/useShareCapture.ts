import { useCallback, useRef } from 'react'
import { captureDomBlob } from '../../lib/captureDom'

/**
 * Share-card capture helper. Returns a ref to wire onto the off-screen card
 * node and a stable `capture()` that screenshots it to a PNG Blob.
 *
 * The caller is responsible for rendering the card inside a
 * `<div className="share-offscreen">` wrapper so 1080px of poster doesn't
 * push the document's scrollbar wider.
 */
export function useShareCapture() {
  const nodeRef = useRef<HTMLDivElement | null>(null)
  const capture = useCallback(async (): Promise<Blob | null> => {
    const node = nodeRef.current
    if (!node) return null
    return captureDomBlob(node)
  }, [])
  return { nodeRef, capture }
}
