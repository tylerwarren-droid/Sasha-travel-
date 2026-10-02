import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'

/**
 * S-80 · the invited guest's page talks to Sasha's server through THIS pass-through: no session, no booking key —
 * only GET /api/booking/invite/{code} and POST …/{code}/choose, which the server leaves open (the 8-character code is
 * the key, rate-limited per address). Anything else is refused here.
 */
async function pass(request: Request, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await ctx.params
  const ok = (request.method === 'GET' && path.length === 1 && /^[A-Z0-9]{8}$/.test(path[0]))
    || (request.method === 'POST' && path.length === 2 && /^[A-Z0-9]{8}$/.test(path[0]) && path[1] === 'choose')
  if (!ok) return NextResponse.json({ ok: false, rule: 'path_refused', message: 'not an invitation route' }, { status: 400 })
  const init: RequestInit = { method: request.method, headers: { 'content-type': 'application/json',
    'x-forwarded-for': request.headers.get('x-forwarded-for') ?? '' }, cache: 'no-store' }
  if (request.method === 'POST') init.body = await request.text()
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/booking/invite/${path.map(encodeURIComponent).join('/')}`, init)
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: `Sasha's server could not be reached (${(e as Error).message})` }, { status: 502 })
  }
  let json: unknown = null
  try { json = await r.json() } catch { /* reported by its status */ }
  return NextResponse.json(json ?? { ok: false, rule: `HTTP ${r.status}` }, { status: r.status })
}

export const GET = pass
export const POST = pass
