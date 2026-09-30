import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { COOKIE, configured, mint, passphraseMatches, valid } from '@/lib/founder-session'

/** S-41 · Is the founder signed in? Says only yes or no — and whether the server is configured at all. */
export async function GET() {
  const store = await cookies()
  return NextResponse.json({ signed_in: valid(store.get(COOKIE)?.value), configured: configured() })
}

/** Sign in with the passphrase. A wrong one is told plainly; nothing about the right one is revealed. */
export async function POST(request: Request) {
  if (!configured()) {
    return NextResponse.json({ ok: false, rule: 'founder_session_not_configured', message: 'FOUNDER_PASSPHRASE and FOUNDER_SESSION_SECRET are not both set on this deployment' }, { status: 503 })
  }
  let body: { passphrase?: unknown } = {}
  try { body = await request.json() } catch { /* an empty body is a wrong passphrase */ }
  if (!passphraseMatches(body.passphrase)) {
    return NextResponse.json({ ok: false, rule: 'passphrase_wrong', message: 'That passphrase is not the founder’s.' }, { status: 401 })
  }
  const { value, maxAge } = mint()
  const store = await cookies()
  store.set(COOKIE, value, { httpOnly: true, secure: true, sameSite: 'strict', path: '/', maxAge })
  return NextResponse.json({ ok: true, signed_in: true })
}

/** Sign out. */
export async function DELETE() {
  const store = await cookies()
  store.delete(COOKIE)
  return NextResponse.json({ ok: true, signed_in: false })
}
