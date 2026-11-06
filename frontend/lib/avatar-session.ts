import { beacon, reach } from '@/lib/request'   // Sasha 348 · the ONE request client
import { observe, toConsole } from '@/lib/outcome'   // Sasha 348 · the ONE outcome path: nothing swallowed
/**
 * Sasha 303 · the page's link to the ONE gate (backend app/avatar_gate.py) for one live face. The gate decides every limit — 60 s with
 * nobody talking, no beat for 30 s (the tab is gone), his minutes, Kanoe's — and closes the session itself on the server. The page
 * only tells it things: a beat every BEAT_MS (open, visible, whether anyone talked), "hidden" when the tab is hidden, "closed" when it
 * goes away (sendBeacon, which outlives the page), and the reason when the page closes it (camera off, leaving).
 */
const BEAT_MS = 15000

export type GateLink = { talk: () => void; close: (why: string) => void; end: () => void }

const send = (action: 'beat' | 'close', body: Record<string, unknown>, leaving = false) => {
  const data = JSON.stringify(body)
  if (leaving) {   // the tab is going: the one client's beacon (it falls back to a keepalive request itself, its failure told)
    beacon(`/api/s2-avatar/${action}`, new Blob([data], { type: 'application/json' }))
    return Promise.resolve(null)
  }
  return reach(`/api/s2-avatar/${action}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: data, keepalive: true })
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
  const close = (why: string, beacon = false) => { if (over) return; end(); observe(send('close', { sid, why }, beacon), 'Closing her face’s session', toConsole) }
  const onVis = () => { if (document.visibilityState === 'hidden') close('hidden', true) }
  const onHide = () => close('closed', true)
  const beat = () => {
    if (over) return
    const t = talked
    talked = false
    observe(send('beat', { sid, talking: t, visible: document.visibilityState === 'visible' }).then(j => { if (j && j.ok === false) end() }), 'Keeping her face’s session', toConsole)
  }
  const timer = setInterval(beat, BEAT_MS)
  document.addEventListener('visibilitychange', onVis)
  window.addEventListener('pagehide', onHide)
  return { talk: () => { talked = true }, close: (why: string) => close(why), end }
}
