/**
 * Sasha 303 · the page's link to the ONE gate (backend app/avatar_gate.py) for one live face. The gate decides every limit — 60 s with
 * nobody talking, no beat for 30 s (the tab is gone), his minutes, Kanoe's — and closes the session itself on the server. The page
 * only tells it things: a beat every BEAT_MS (open, visible, whether anyone talked), "hidden" when the tab is hidden, "closed" when it
 * goes away (sendBeacon, which outlives the page), and the reason when the page closes it (camera off, leaving).
 */
const BEAT_MS = 15000

export type GateLink = { talk: () => void; close: (why: string) => void; end: () => void }

const send = (action: 'beat' | 'close', body: Record<string, unknown>, beacon = false) => {
  const data = JSON.stringify(body)
  try {
    if (beacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
      navigator.sendBeacon(`/api/s2-avatar/${action}`, new Blob([data], { type: 'application/json' }))
      return Promise.resolve(null)
    }
  } catch { /* the fetch below */ }
  return fetch(`/api/s2-avatar/${action}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: data, keepalive: true })
    .then(r => r.json().catch(() => null)).catch(() => null)
}

export function gateLink(sid: string): GateLink {
  let talked = false
  let over = false
  const end = () => {
    if (over) return
    over = true
    clearInterval(timer)
    document.removeEventListener('visibilitychange', onVis)
    window.removeEventListener('pagehide', onHide)
  }
  const close = (why: string, beacon = false) => { if (over) return; end(); void send('close', { sid, why }, beacon) }
  const onVis = () => { if (document.visibilityState === 'hidden') close('hidden', true) }
  const onHide = () => close('closed', true)
  const beat = () => {
    if (over) return
    const t = talked
    talked = false
    void send('beat', { sid, talking: t, visible: document.visibilityState === 'visible' }).then(j => { if (j && j.ok === false) end() })
  }
  const timer = setInterval(beat, BEAT_MS)
  document.addEventListener('visibilitychange', onVis)
  window.addEventListener('pagehide', onHide)
  return { talk: () => { talked = true }, close: (why: string) => close(why), end }
}
