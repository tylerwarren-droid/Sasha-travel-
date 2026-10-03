import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'

/**
 * CR 1 · the public door to /api/booking/products/* — GET only (a hand-over page's calendar file, a relocation file's
 * PDF). The booking key is added here and never reaches the browser; the id in the path is the capability the backend
 * checks. Nothing else is forwarded.
 */
export async function GET(request: Request, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
  if (!key) return NextResponse.json({ ok: false, message: 'SASHA_BOOKING_KEY is not set on this deployment' }, { status: 503 })
  const { path } = await ctx.params
  if (!path.length || path.some((p) => p === '..' || p === '' || !/^[\w\-.]+$/.test(p))) {
    return NextResponse.json({ ok: false, message: 'not a product page' }, { status: 400 })
  }
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/booking/products/${path.join('/')}`, { headers: { 'x-sasha-booking-key': key }, cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, message: `Sasha's server could not be reached (${(e as Error).message})` }, { status: 502 })
  }
  const headers = new Headers()
  for (const h of ['content-type', 'content-disposition']) {
    const v = r.headers.get(h)
    if (v) headers.set(h, v)
  }
  return new Response(await r.arrayBuffer(), { status: r.status, headers })
}
