import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/** Sasha 248 · ONE PLACE CARD's detail sheet (/s2 and /next): a place on the person's screen, its facts from the venue engine —
 *  the site's own words with their sources; Google's category only labelled. */
export const dynamic = 'force-dynamic'
export const maxDuration = 90

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  const who = await agentHeaders()
  if (!who) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  const { id } = await params
  try {
    const r = await fetch(`${API_URL}/api/agent/place/${encodeURIComponent(id.slice(0, 200))}`, { headers: who, cache: 'no-store' })
    return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
}
