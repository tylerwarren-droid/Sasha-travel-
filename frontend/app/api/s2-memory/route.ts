import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/** Sasha 231 · /s2 on return: what Sasha remembers for this account (masked) — "Welcome back — we were looking at …", the recent
 *  conversation and the cards she'd shown. The backend puts those cards back on screen for this page's session. */
export const dynamic = 'force-dynamic'

export async function GET(request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  const q = new URL(request.url).searchParams
  const session = q.get('session')?.slice(0, 64) ?? ''
  // Sasha 296 · ?pickup=1: her first words after a return (backend /s2/pickup — read only: no recall, no news taken)
  const to = q.get('pickup') === '1' ? `${API_URL}/api/agent/s2/pickup` : `${API_URL}/api/agent/s2/memory?session=${encodeURIComponent(session)}`
  try {
    const r = await fetch(to, { headers: { ...who, 'x-sasha-surface': 's2' }, cache: 'no-store' })
    return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
}

/** Sasha 265 · item 3 · New chat on /s2: the same one clear as /next (backend DELETE /api/agent/memory). */
export async function DELETE(): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  try {
    const r = await fetch(`${API_URL}/api/agent/memory`, { method: 'DELETE', headers: { ...who, 'x-sasha-surface': 's2' }, cache: 'no-store' })
    return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
}
