import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'
import { mintSession } from '@/lib/avatar-mint'

/**
 * Sasha 225 · /s2's live face: a LiveAvatar session in LITE mode — her face only, speaking exactly the audio /s2 sends.
 * Sasha 303 · THROUGH THE ONE GATE (backend app/avatar_gate.py): the gate is asked first (a real signed-in person's tap on /s2,
 * under his minutes and Kanoe's); only on its yes is a token minted (lib/avatar-mint.ts), and the token goes to the gate at once —
 * it holds it and closes the session (quiet, hidden, closed, a cap). A refusal: {ok:false, rule, say?} — her still, and (a cap)
 * the one line she says.
 */
export const dynamic = 'force-dynamic'

const json = (b: unknown, status = 200) => NextResponse.json(b, { status, headers: { 'cache-control': 'no-store' } })

export async function POST(request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return json({ ok: false, rule: 'sign_in_required' }, 401)
  const { why } = await request.json().catch(() => ({ why: '' }))
  const post = (path: string, body: unknown) => fetch(`${API_URL}${path}`, {
    method: 'POST', headers: { ...who, 'content-type': 'application/json' }, body: JSON.stringify(body), cache: 'no-store' })
  try {
    const g = await post('/api/avatar/open', { surface: 's2', why: String(why || '') })
    const yes = await g.json().catch(() => ({}))
    if (!g.ok || !yes?.ok || !yes?.sid) return json({ ok: false, rule: yes?.rule || 'refused', ...(yes?.say ? { say: yes.say } : {}) }, 403)
    const m = await mintSession()
    if ('error' in m) {
      await post('/api/avatar/close', { sid: yes.sid, why: 'not_minted' }).catch(() => null)
      return json({ ok: false, rule: m.error }, m.status)
    }
    const held = await post('/api/avatar/opened', { sid: yes.sid, token: m.token, session_id: m.sessionId })
    if (!held.ok) return json({ ok: false, rule: 'not_held' }, 502)   // the gate stopped it: it never reaches the page
    return json({ ok: true, token: m.token, sid: yes.sid })
  } catch (e) {
    return json({ ok: false, rule: 'unreachable', message: (e as Error).name }, 502)
  }
}
