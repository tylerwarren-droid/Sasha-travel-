import { API_URL } from '@/lib/api'

/**
 * CR 1 · server-side reads of /api/booking/products/* (CampusMe hand-overs, relocation files). The booking key stays on
 * the server; no identity is sent — the page's id is its capability, checked by the backend (backend/products/routes.py).
 * Only GET, only under /products/.
 */
export type ProductsResult<T> = { ok: true; data: T } | { ok: false; status: number; message: string }

export async function productsGet<T>(path: string): Promise<ProductsResult<T>> {
  const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
  if (!key) return { ok: false, status: 503, message: 'This page can’t reach Sasha’s server from here (SASHA_BOOKING_KEY is not set on this deployment).' }
  if (!/^\/[\w\-./]+$/.test(path) || path.includes('..')) return { ok: false, status: 400, message: 'Not a product page.' }
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/booking/products${path}`, { headers: { 'x-sasha-booking-key': key }, cache: 'no-store' })
  } catch (e) {
    return { ok: false, status: 502, message: `Sasha’s server could not be reached (${(e as Error).message}).` }
  }
  if (!r.ok) {
    let message = `Sasha’s server answered HTTP ${r.status}.`
    try {
      const j = await r.json()
      const d = j && typeof j === 'object' && 'detail' in j ? (j as { detail: { message?: string } }).detail : j
      if (d && typeof d === 'object' && 'message' in d && typeof d.message === 'string') message = d.message
    } catch { /* the status says it */ }
    return { ok: false, status: r.status, message }
  }
  return { ok: true, data: (await r.json()) as T }
}
