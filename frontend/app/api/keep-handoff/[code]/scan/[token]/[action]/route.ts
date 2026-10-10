import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'

/** Sasha 228 · the phone's Confirm (→ saved encrypted in the account's Keep; the code is spent) or Retake (→ that reading dropped). */
export const dynamic = 'force-dynamic'

export async function POST(_request: Request, { params }: { params: Promise<{ code: string; token: string; action: string }> }): Promise<Response> {
  const { code, token, action } = await params
  if (action !== 'confirm' && action !== 'discard') return NextResponse.json({ ok: false, rule: 'unknown_action' }, { status: 404 })
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/keep/handoff/${encodeURIComponent(code)}/${encodeURIComponent(token)}/${action}`, { method: 'POST', cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
}
