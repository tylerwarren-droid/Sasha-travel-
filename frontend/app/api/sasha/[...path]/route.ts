import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { API_URL, CLIENT_KEY } from '@/lib/api'
import { COOKIE, valid } from '@/lib/founder-session'

/**
 * Sasha 142 · THE FOUNDER'S CHAT PASS-THROUGH. Since Sasha 142 a web visitor with no sign-in is the PUBLIC demo account
 * (its own, empty), never the founder's: before it, a phone that wasn't signed in was shown his itinerary (CR's
 * finding, 4 Oct 2026). The founder's own web chat keeps his account by coming through HERE: this checks his session
 * cookie and only then calls the backend with `x-sasha-session: founder` and SASHA_BOOKING_KEY, which the browser
 * never sees. The backend accepts the header only with the key (app/services/chat_account.py).
 *
 * ⛔ No founder session → 401, nothing forwarded (guests and visitors call the backend directly, as before). Only the
 * account-scoped chat routes below are forwarded; the booking routes have their own proxy.
 */
const ROUTES = ['agents/conductor', 'agents/classify', 'voice/conductor', 'trips', 'chats', 'payments/verify', 'payments/reserve', 'payments/create-checkout']

export const maxDuration = 60   // a conductor turn: the chat's own timeout is 60 s

async function pass(request: Request, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const store = await cookies()
  if (!valid(store.get(COOKIE)?.value)) {
    return NextResponse.json({ ok: false, rule: 'founder_session_required', message: 'This pass-through is the founder’s own session only.' }, { status: 401 })
  }
  const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
  if (!key) {
    return NextResponse.json({ ok: false, rule: 'booking_key_not_configured', message: 'SASHA_BOOKING_KEY is not set on this deployment' }, { status: 503 })
  }
  const { path } = await ctx.params
  if (path.some((p) => p === '..' || p === '' || p.includes('/'))) {
    return NextResponse.json({ ok: false, rule: 'path_refused', message: 'not a chat route' }, { status: 400 })
  }
  const joined = path.join('/')
  if (!ROUTES.some((r) => joined === r || joined.startsWith(`${r}/`))) {
    return NextResponse.json({ ok: false, rule: 'path_refused', message: 'not a chat route' }, { status: 400 })
  }
  const url = `${API_URL}/api/${path.map(encodeURIComponent).join('/')}${new URL(request.url).search}`
  // the body is passed as it came (JSON, or the voice page's multipart audio), with its own content type
  const headers: Record<string, string> = { 'content-type': request.headers.get('content-type') ?? 'application/json', 'x-sasha-session': 'founder', 'x-sasha-booking-key': key }
  if (CLIENT_KEY) headers['X-Client-Key'] = CLIENT_KEY
  // Sasha 159 · the founder's address, so guests on his devices and wifi are never capped
  const ip = (request.headers.get('x-forwarded-for') ?? '').split(',')[0].trim() || request.headers.get('x-real-ip') || ''
  if (ip) headers['x-sasha-client-ip'] = ip
  const init: RequestInit = { method: request.method, headers, cache: 'no-store' }
  if (request.method !== 'GET') init.body = await request.arrayBuffer()
  let r: Response
  try {
    r = await fetch(url, init)
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: `Sasha's server could not be reached (${(e as Error).message})` }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': r.headers.get('content-type') ?? 'application/json' } })
}

export const GET = pass
export const POST = pass
