import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { API_URL, CLIENT_KEY } from '@/lib/api'
import { COOKIE, valid } from '@/lib/founder-session'

/** Sasha 204 · /next's own measure of each voice turn (first sound, full answer), passed to the server log. Founder only. */
export async function POST(request: Request): Promise<Response> {
  const store = await cookies()
  if (!valid(store.get(COOKIE)?.value)) return NextResponse.json({ ok: false }, { status: 401 })
  const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
  const headers: Record<string, string> = { 'content-type': 'application/json', 'x-sasha-session': 'founder', 'x-sasha-booking-key': key }
  if (CLIENT_KEY) headers['X-Client-Key'] = CLIENT_KEY
  const r = await fetch(`${API_URL}/api/agent/timing`, { method: 'POST', headers, body: await request.text(), cache: 'no-store' }).catch(() => null)
  return NextResponse.json({ ok: !!r?.ok }, { status: r?.ok ? 200 : 502 })
}
