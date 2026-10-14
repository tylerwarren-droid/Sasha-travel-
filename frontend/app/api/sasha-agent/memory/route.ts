import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/** Sasha 241 · S1 PARITY: /next's welcome back — the same memory as /s2 (one per account), from the backend's /api/agent/memory.
 *  Signed-in only; the session is the chat's own, so her first turn back hears what was (and wasn't) decided. */
export const dynamic = 'force-dynamic'

export async function GET(request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  const session = new URL(request.url).searchParams.get('session')?.slice(0, 64) ?? ''
  try {
    const r = await fetch(`${API_URL}/api/agent/memory?session=${encodeURIComponent(session)}`, { headers: { ...who }, cache: 'no-store' })
    return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
}

/** Sasha 265 · item 3 · New chat on /next: the conversation cleared in the one conversation record (backend DELETE /api/agent/memory). */
export async function DELETE(): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  try {
    const r = await fetch(`${API_URL}/api/agent/memory`, { method: 'DELETE', headers: { ...who }, cache: 'no-store' })
    return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
}
