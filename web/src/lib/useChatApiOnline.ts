import { useEffect, useState } from 'react'

/**
 * Probe whether the chat backend is reachable. Used to disable role-play
 * and "与 X 聊聊" entry points when `uv run api` isn't running.
 *
 * Content-type + shape guards keep a static-SPA deploy (where every unknown
 * path returns index.html) from being mistaken for an online API.
 *
 * Returns `null` while probing, `true` when reachable, `false` when not.
 */
export function useChatApiOnline(): boolean | null {
  const [online, setOnline] = useState<boolean | null>(null)
  useEffect(() => {
    let alive = true
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), 1500)
    fetch('/api/agents', { signal: ctl.signal })
      .then(async r => {
        if (!alive) return
        if (!r.ok) {
          setOnline(false)
          return
        }
        const ct = r.headers.get('content-type') ?? ''
        if (!ct.includes('application/json')) {
          setOnline(false)
          return
        }
        try {
          const body = await r.json()
          setOnline(
            typeof body === 'object' && body !== null && 'agents' in body,
          )
        } catch {
          setOnline(false)
        }
      })
      .catch(() => {
        if (alive) setOnline(false)
      })
      .finally(() => clearTimeout(timer))
    return () => {
      alive = false
      ctl.abort()
      clearTimeout(timer)
    }
  }, [])
  return online
}
