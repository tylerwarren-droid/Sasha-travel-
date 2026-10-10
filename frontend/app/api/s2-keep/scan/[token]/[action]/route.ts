import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/** Sasha 224 · the masked card's Confirm (→ saved encrypted in the Keep) or Retake (→ the reading dropped). */
export const dynamic = 'force-dynamic'

export async function POST(_request: Request, { params }: { params: Promise<{ token: string; action: string }> }): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  const { token, action } = await params
  if (action !== 'confirm' && action !== 'discard') return NextResponse.json({ ok: false, rule: 'unknown_action' }, { status: 404 })
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/keep/scan/${encodeURIComponent(token)}/${action}`, { method: 'POST', headers: who, cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
}
