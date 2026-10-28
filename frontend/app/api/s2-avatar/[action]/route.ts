import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/** Sasha 303 · the page's word to the ONE gate (backend app/avatar_gate.py) about the live face it holds: `beat` (open, visible,
 *  talking) and `close` (camera off, leaving, a hidden or closed tab — sent with sendBeacon). The gate decides; this only carries. */
export const dynamic = 'force-dynamic'

export async function POST(request: Request, { params }: { params: Promise<{ action: string }> }): Promise<Response> {
  const { action } = await params
  if (action !== 'beat' && action !== 'close') return NextResponse.json({ ok: false, rule: 'not_found' }, { status: 404 })
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  const body = await request.text().catch(() => '{}')
  try {
    const r = await fetch(`${API_URL}/api/avatar/${action}`, { method: 'POST', headers: { ...who, 'content-type': 'application/json' }, body, cache: 'no-store' })
    return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).name }, { status: 502 })
  }
}
