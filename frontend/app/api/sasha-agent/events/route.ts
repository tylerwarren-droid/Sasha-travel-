import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/**
 * Sasha 212 · /next's LIVE CHANNEL (backend /api/agent/events, server-sent events): a payment that completes on the phone
 * reaches the open page the moment it's booked — the person does nothing. Same rule as /api/sasha-agent: his session
 * cookie, else 401. The stream ends with this function's time limit; EventSource reconnects on its own, sending the last
 * id it heard (Last-Event-ID), so nothing is heard twice or missed.
 */
export const maxDuration = 300
export const dynamic = 'force-dynamic'

export async function GET(request: Request): Promise<Response> {
  const headers = await agentHeaders()   // Sasha 213 · the founder, or a signed-in guest (their own events only)
  if (!headers) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  const url = new URL(request.url)
  const since = request.headers.get('last-event-id') || url.searchParams.get('since') || '0'
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/events?since=${encodeURIComponent(since)}`, { headers, cache: 'no-store', signal: request.signal })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  if (!r.ok || !r.body) return new Response(await r.text(), { status: r.status })
  return new Response(r.body, { status: 200, headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache, no-transform', 'x-accel-buffering': 'no' } })
}
