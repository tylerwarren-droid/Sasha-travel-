import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { API_URL, CLIENT_KEY } from '@/lib/api'
import { COOKIE, valid } from '@/lib/founder-session'

/**
 * Sasha 203 · /next — the founder's pass-through to Sasha's AGENT (backend /api/agent/turn), STREAMED: the agent's events
 * (text as it is written, each tool call, "the trip changed") reach the page as they happen. Same rule as /api/sasha:
 * his session cookie, else 401; the booking key never reaches the browser. Alongside the current Sasha — nothing shared.
 */
export const maxDuration = 120   // an agent turn can call several tools
export const dynamic = 'force-dynamic'

export async function POST(request: Request): Promise<Response> {
  const store = await cookies()
  if (!valid(store.get(COOKIE)?.value)) {
    return NextResponse.json({ ok: false, rule: 'founder_session_required', message: 'Sasha’s agent (/next) is the founder’s own session for now.' }, { status: 401 })
  }
  const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
  if (!key) return NextResponse.json({ ok: false, rule: 'booking_key_not_configured' }, { status: 503 })
  const headers: Record<string, string> = { 'content-type': 'application/json', 'x-sasha-session': 'founder', 'x-sasha-booking-key': key }
  if (CLIENT_KEY) headers['X-Client-Key'] = CLIENT_KEY
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/turn`, { method: 'POST', headers, body: await request.text(), cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  if (!r.ok || !r.body) return new Response(await r.text(), { status: r.status, headers: { 'content-type': r.headers.get('content-type') ?? 'application/json' } })
  return new Response(r.body, { status: 200, headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache, no-transform', 'x-accel-buffering': 'no' } })
}
