import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'

/** Sasha 228 · the phone's passport photo, under a one-time "Add from your phone" code: straight through to the backend, which
 *  reads it once and drops it (keep_scan) — nothing stored here, nothing logged. Back: a MASKED card to confirm. */
export const maxDuration = 60
export const dynamic = 'force-dynamic'

export async function POST(request: Request, { params }: { params: Promise<{ code: string }> }): Promise<Response> {
  const { code } = await params
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/keep/handoff/${encodeURIComponent(code)}/scan`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: await request.text(), cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
}
