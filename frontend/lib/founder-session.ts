/**
 * S-41 · The founder's session — the only way a browser reaches the booking routes.
 *
 * A signed, HttpOnly cookie `sasha_founder` = "<expiry ms>.<HMAC-SHA256(expiry) with FOUNDER_SESSION_SECRET>", set after
 * the passphrase (FOUNDER_PASSPHRASE) is given to /api/founder-session. The booking pass-through
 * (/api/booking-proxy/…) checks it, and only then adds the backend's SASHA_BOOKING_KEY — which never reaches the browser.
 *
 * SERVER ONLY: it reads secrets from the environment. ⛔ Fails closed: with either secret unset, nobody is signed in.
 */
import { createHmac, timingSafeEqual } from 'node:crypto'

export const COOKIE = 'sasha_founder'
export const SESSION_HOURS = 12

const secret = () => (process.env.FOUNDER_SESSION_SECRET ?? '').trim()

const mac = (payload: string) => createHmac('sha256', secret()).update(payload).digest('base64url')

function same(a: string, b: string): boolean {
  const x = Buffer.from(a), y = Buffer.from(b)
  return x.length === y.length && timingSafeEqual(x, y)
}

export function configured(): boolean {
  return secret().length >= 32 && (process.env.FOUNDER_PASSPHRASE ?? '').trim().length >= 12
}

export function passphraseMatches(given: unknown): boolean {
  const want = (process.env.FOUNDER_PASSPHRASE ?? '').trim()
  return configured() && typeof given === 'string' && same(given, want)
}

export function mint(now = Date.now()): { value: string; maxAge: number } {
  const exp = String(now + SESSION_HOURS * 3600 * 1000)
  return { value: `${exp}.${mac(exp)}`, maxAge: SESSION_HOURS * 3600 }
}

export function valid(value: string | undefined, now = Date.now()): boolean {
  if (!configured() || !value) return false
  const [exp, sig] = value.split('.')
  if (!exp || !sig || !/^\d+$/.test(exp) || Number(exp) <= now) return false
  return same(sig, mac(exp))
}
