import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'

/**
 * S-55 · The Work-with-Sasha pass-through. PUBLIC: a venue has no founder session. It forwards ONLY the six opt-in
 * actions below to the backend's /api/booking/optin/…, adding SASHA_BOOKING_KEY server-side (the browser never sees
 * it). Every other booking route stays behind the founder session in /api/booking-proxy.
 */
const ACTIONS: Record<string, { method: 'GET' | 'POST'; path: string }> = {
  status: { method: 'GET', path: 'status' },
  wordings: { method: 'GET', path: 'wordings' },
  request: { method: 'POST', path: 'requests' },
  preview: { method: 'POST', path: 'preview' },
  confirm: { method: 'POST', path: 'confirm' },
  withdraw: { method: 'POST', path: 'withdraw' },
}

async function pass(request: Request, ctx: { params: Promise<{ action: string }> }): Promise<Response> {
  const { action } = await ctx.params
  const a = ACTIONS[action]
  if (!a || a.method !== request.method) {
    return NextResponse.json({ ok: false, rule: 'not_an_optin_action', message: 'not a Work-with-Sasha action' }, { status: 404 })
  }
  const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
  if (!key) {
    return NextResponse.json({ ok: false, rule: 'booking_key_not_configured', message: 'SASHA_BOOKING_KEY is not set on this deployment' }, { status: 503 })
  }
  const lang = new URL(request.url).searchParams.get('lang')
  const q = action === 'wordings' && (lang === 'en' || lang === 'es') ? `?lang=${lang}` : ''
  const init: RequestInit = { method: a.method, headers: { 'content-type': 'application/json', 'x-sasha-booking-key': key }, cache: 'no-store' }
  if (a.method === 'POST') init.body = await request.text()
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/booking/optin/${a.path}${q}`, init)
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: `Sasha's server could not be reached (${(e as Error).message})` }, { status: 502 })
  }
  let json: unknown = null
  try { json = await r.json() } catch { /* reported by its status */ }
  const flat = json && typeof json === 'object' && 'detail' in (json as object) && typeof (json as { detail: unknown }).detail === 'object'
    ? (json as { detail: object }).detail : json
  return NextResponse.json(flat ?? { ok: false, rule: `HTTP ${r.status}` }, { status: r.status })
}

export const GET = pass
export const POST = pass
