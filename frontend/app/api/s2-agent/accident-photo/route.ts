import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/**
 * CR 75 · /s2's accident card: one guided photo (downscaled on the phone) straight to the backend, which hands it to AgAPI — sealed
 * under the person's own key and recorded as hashed evidence. Nothing is stored or logged here; it never goes through the chat.
 */
export const maxDuration = 60
export const dynamic = 'force-dynamic'

export async function POST(request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/s2/accident-photo`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-sasha-surface': 's2', ...who },
      body: await request.text(), cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
}
