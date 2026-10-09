import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/**
 * CR 62 · the ACTIVITY view's data (backend GET /api/agent/activity): everything Sasha did for the signed-in person, newest
 * first, each row with its proof. Same rule as /api/sasha-agent: the founder's session, or a signed-in guest's own (their
 * token, verified by the backend) — else 401. Read-only.
 */
export const dynamic = 'force-dynamic'

export async function GET(request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required', message: 'Please sign in first — /sign-in.' }, { status: 401 })
  const since = new URL(request.url).searchParams.get('since') ?? ''
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/activity${since ? `?since=${encodeURIComponent(since)}` : ''}`, { headers: who, cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': r.headers.get('content-type') ?? 'application/json' } })
}
