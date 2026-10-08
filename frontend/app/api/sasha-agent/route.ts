import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/**
 * Sasha 203 · /next — the founder's pass-through to Sasha's AGENT (backend /api/agent/turn), STREAMED: the agent's events
 * (text as it is written, each tool call, "the trip changed") reach the page as they happen. Same rule as /api/sasha:
 * his session cookie, else 401; the booking key never reaches the browser. Alongside the current Sasha — nothing shared.
 */
export const maxDuration = 120   // an agent turn can call several tools
export const dynamic = 'force-dynamic'

export async function POST(request: Request): Promise<Response> {
  // Sasha 213 · the founder's session, or a signed-in guest's own (their token, verified by the backend) — else 401
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required', message: 'Please sign in first — /sign-in.' }, { status: 401 })
  const headers: Record<string, string> = { 'content-type': 'application/json', ...who }
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/turn`, { method: 'POST', headers, body: await request.text(), cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  if (!r.ok || !r.body) return new Response(await r.text(), { status: r.status, headers: { 'content-type': r.headers.get('content-type') ?? 'application/json' } })
  return new Response(r.body, { status: 200, headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache, no-transform', 'x-accel-buffering': 'no' } })
}
