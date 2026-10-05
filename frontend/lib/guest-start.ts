'use client'

/**
 * Sasha 153 · NO SIGN-IN WALL: make sure this browser has an account — the founder's, a guest's, or a NEW automatic private
 * guest account (/api/guest/start). Asked once per page; the answer is shared by every caller.
 */
let pending: Promise<boolean> | null = null

export function ensureGuest(): Promise<boolean> {
  if (!pending) {
    pending = fetch('/api/guest/start', { method: 'POST', cache: 'no-store' })
      .then(async (r) => r.ok && (await r.json().catch(() => ({})))?.ok === true)
      .catch(() => false)
      .then((ok) => { if (!ok) pending = null; return ok })   // a failure can be retried on the next action
  }
  return pending
}

/** Sasha 153 · after a booking, the "Keep this across devices" offer appears (never before one) */
export const BOOKED_EVENT = 'sasha:booked'
export function announceBooked(): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(BOOKED_EVENT))
}
