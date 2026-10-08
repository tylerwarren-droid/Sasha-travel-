import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { agentHeaders } from '@/lib/agent-auth'

/** Sasha 204 · /next's own measure of each voice turn (first sound, full answer), passed to the server log. Founder only. */
export async function POST(request: Request): Promise<Response> {
  const who = await agentHeaders()   // Sasha 213 · the founder, or a signed-in guest
  if (!who) return NextResponse.json({ ok: false }, { status: 401 })
  const headers: Record<string, string> = { 'content-type': 'application/json', ...who }
  const r = await fetch(`${API_URL}/api/agent/timing`, { method: 'POST', headers, body: await request.text(), cache: 'no-store' }).catch(() => null)
  return NextResponse.json({ ok: !!r?.ok }, { status: r?.ok ? 200 : 502 })
}
