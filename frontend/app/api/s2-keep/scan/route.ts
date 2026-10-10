import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/**
 * Sasha 224 · /s2's "add to my Keep from a photo": the photo (downscaled on the phone) goes straight through to the backend,
 * which reads it once and drops it — nothing is stored here, nothing is logged. Back: a MASKED card to confirm (nothing saved yet).
 */
export const maxDuration = 60
export const dynamic = 'force-dynamic'

export async function POST(request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/keep/scan`, { method: 'POST', headers: { 'content-type': 'application/json', ...who }, body: await request.text(), cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
}
