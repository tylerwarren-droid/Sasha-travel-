/**
 * S-41 · Booking calls go through the frontend's own server (/api/booking-proxy/…), never straight to the backend:
 * that server checks the founder's session and adds the booking key the browser never holds.
 */
export const bookingUrl = (path: string): string => {
  const p = path.startsWith('/') ? path : `/${path}`
  if (!p.startsWith('/api/booking/')) throw new Error(`not a booking route: ${p}`)
  return `/api/booking-proxy/${p.slice('/api/booking/'.length)}`
}

export const bookingHeaders = (): Record<string, string> => ({ 'Content-Type': 'application/json' })
