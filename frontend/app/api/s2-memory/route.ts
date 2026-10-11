import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/** Sasha 231 · /s2 on return: what Sasha remembers for this account (masked) — "Welcome back — we were looking at …", the recent
 *  conversation and the cards she'd shown. The backend puts those cards back on screen for this page's session. */
export const dynamic = 'force-dynamic'

export async function GET(request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  const session = new URL(request.url).searchParams.get('session')?.slice(0, 64) ?? ''
  try {
    const r = await fetch(`${API_URL}/api/agent/s2/memory?session=${encodeURIComponent(session)}`, { headers: { ...who, 'x-sasha-surface': 's2' }, cache: 'no-store' })
    return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
}
