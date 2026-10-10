import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'

/** Sasha 228 · is this one-time "Add from your phone" code still open? Nothing about the account comes back. No sign-in: the
 *  code is the only permission (backend agapi/keep_handoff.py). */
export const dynamic = 'force-dynamic'

export async function GET(_request: Request, { params }: { params: Promise<{ code: string }> }): Promise<Response> {
  const { code } = await params
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/keep/handoff/${encodeURIComponent(code)}`, { cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
}
