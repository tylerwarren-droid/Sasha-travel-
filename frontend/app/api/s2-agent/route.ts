import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/**
 * Sasha 221 · /s2's pass-through to Sasha's agent — the SAME agent as /next (backend /api/agent/turn), streamed, with ONE
 * difference: it says it's S2 (x-sasha-surface: s2), which picks S2's opening lines, tool set and demo setting. Only this
 * route sends it; /next's /api/sasha-agent never does. Same rule: the founder's session or a signed-in guest's, else 401.
 */
export const maxDuration = 120
export const dynamic = 'force-dynamic'

export async function POST(request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required', message: 'Please sign in first.' }, { status: 401 })
  const headers: Record<string, string> = { 'content-type': 'application/json', 'x-sasha-surface': 's2', ...who }
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/turn`, { method: 'POST', headers, body: await request.text(), cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  if (!r.ok || !r.body) return new Response(await r.text(), { status: r.status, headers: { 'content-type': r.headers.get('content-type') ?? 'application/json' } })
  return new Response(r.body, { status: 200, headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache, no-transform', 'x-accel-buffering': 'no' } })
}
