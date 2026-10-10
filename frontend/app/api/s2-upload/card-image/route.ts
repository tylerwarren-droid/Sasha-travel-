import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/**
 * Sasha 226 · /s2's paperclip → "A card": the photo or Wallet screenshot (shrunk on the phone) goes straight through to the
 * backend, which keeps it in MEMORY for 10 minutes (never on disk) and hands back a card_image_ref for add_card.
 * Nothing is stored here, nothing is logged.
 */
export const maxDuration = 60
export const dynamic = 'force-dynamic'

export async function POST(request: Request): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/agent/s2/card-image`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-sasha-surface': 's2', ...who }, body: await request.text(), cache: 'no-store' })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
}
