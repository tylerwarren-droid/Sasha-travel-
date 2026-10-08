import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { API_URL, CLIENT_KEY } from '@/lib/api'
import { COOKIE, valid } from '@/lib/founder-session'

/**
 * Sasha 212 · /next's LIVE CHANNEL (backend /api/agent/events, server-sent events): a payment that completes on the phone
 * reaches the open page the moment it's booked — the person does nothing. Same rule as /api/sasha-agent: his session
 * cookie, else 401. The stream ends with this function's time limit; EventSource reconnects on its own, sending the last
 * id it heard (Last-Event-ID), so nothing is heard twice or missed.
 */
export const maxDuration = 300
export const dynamic = 'force-dynamic'

export async function GET(request: Request): Promise<Response> {
  const store = await cookies()
  if (!valid(store.get(COOKIE)?.value)) {
    return NextResponse.json({ ok: false, rule: 'founder_session_required' }, { status: 401 })
  }
  const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
  if (!key) return NextResponse.json({ ok: false, rule: 'booking_key_not_configured' }, { status: 503 })
  const url = new URL(request.url)
  const since = request.headers.get('last-event-id') || url.searchParams.get('since') || '0'
  const headers: Record<string, string> = { 'x-sasha-session': 'founder', 'x-sasha-booking-key': key }
  if (CLIENT_KEY) headers['X-Client-Key'] = CLIENT_KEY
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/events?since=${encodeURIComponent(since)}`, { headers, cache: 'no-store', signal: request.signal })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  if (!r.ok || !r.body) return new Response(await r.text(), { status: r.status })
  return new Response(r.body, { status: 200, headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache, no-transform', 'x-accel-buffering': 'no' } })
}
