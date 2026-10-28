import { NextResponse } from 'next/server'

/**
 * Sasha 303 · RETIRED — this route minted a FULL LiveAvatar (HeyGen) session for ANY visitor, no sign-in (/vietnam, /next, the site
 * root opened one on page load). Every avatar session now opens through the ONE gate (backend app/avatar_gate.py, via
 * /api/s2-avatar/token): a real signed-in person's tap on /s2 only. This answers with her still (SashaAvatar shows it); nothing is minted.
 */
export const dynamic = 'force-dynamic'

export async function GET(): Promise<Response> {
  return NextResponse.json({ ok: false, rule: 'avatar_closed', say: 'Her video is on /s2 only.' }, { status: 403, headers: { 'cache-control': 'no-store' } })
}
