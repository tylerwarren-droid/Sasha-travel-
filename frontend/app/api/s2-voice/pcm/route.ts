import { NextResponse } from 'next/server'
import { agentHeaders } from '@/lib/agent-auth'

/** Sasha 225 · her voice as raw 24 kHz 16-bit PCM (base64) — what the LITE avatar lip-syncs to. The SAME voice as /s2's spoken
 *  replies (Deepgram aura-asteria-en, as /api/voice/tts), so the hello and everything after sound like one person. */
export const dynamic = 'force-dynamic'

export async function POST(request: Request): Promise<Response> {
  if (!(await agentHeaders())) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  const key = (process.env.DEEPGRAM_API_KEY ?? '').trim()
  if (!key) return NextResponse.json({ ok: false, rule: 'not_configured' }, { status: 503 })
  const { text } = await request.json().catch(() => ({ text: '' }))
  const t = String(text ?? '').replace(/[*#]/g, '').replace(/→/g, 'to').slice(0, 600).trim()
  if (!t) return NextResponse.json({ ok: false, rule: 'empty' }, { status: 400 })
  const r = await fetch('https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=24000&container=none', {
    method: 'POST', headers: { Authorization: `Token ${key}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ text: t }), cache: 'no-store',
  }).catch(() => null)
  if (!r || !r.ok) return NextResponse.json({ ok: false, rule: 'tts_failed', status: r?.status ?? 0 }, { status: 502 })
  const audio = Buffer.from(await r.arrayBuffer()).toString('base64')
  return NextResponse.json({ ok: true, audio }, { headers: { 'cache-control': 'no-store' } })
}
