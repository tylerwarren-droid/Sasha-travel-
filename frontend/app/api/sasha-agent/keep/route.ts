import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/**
 * CR 63 · THE KEEP's pass-through (backend /api/agent/keep): list (masks only), save (the value goes from the person's own
 * form straight to the backend, where it's sealed — it is never logged here), and delete everything (?confirm=DELETE).
 * The founder's session or a signed-in guest's own — else 401.
 */
export const dynamic = 'force-dynamic'

async function pass(method: 'GET' | 'POST' | 'DELETE', request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required', message: 'Please sign in first — /sign-in.' }, { status: 401 })
  const q = new URL(request.url).searchParams.get('confirm')
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/keep${q ? `?confirm=${encodeURIComponent(q)}` : ''}`, {
      method, cache: 'no-store',
      headers: { ...who, ...(method === 'POST' ? { 'content-type': 'application/json' } : {}) },
      ...(method === 'POST' ? { body: await request.text() } : {}),
    })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
}

export const GET = (r: Request) => pass('GET', r)
export const POST = (r: Request) => pass('POST', r)
export const DELETE = (r: Request) => pass('DELETE', r)
