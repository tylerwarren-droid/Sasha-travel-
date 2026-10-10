import { NextResponse } from 'next/server'
import { agentHeaders } from '@/lib/agent-auth'

/**
 * Sasha 225 · /s2's avatar hello: a LiveAvatar session in LITE mode — her face only. It speaks exactly the audio /s2 sends
 * (her own voice, the same one she uses after the hand-off: /api/s2-voice/pcm), with no context and no opening line of its own.
 * Signed-in only. /next's token route (/api/heygen/token) is untouched.
 */
export const dynamic = 'force-dynamic'

const AVATAR_ID = 'ab0765ad-69de-41fb-9f8a-bd01c3c52d6f'   // the same face as /next

export async function GET(): Promise<Response> {
  if (!(await agentHeaders())) return NextResponse.json({ ok: false, rule: 'sign_in_required' }, { status: 401 })
  if (!process.env.HEYGEN_API_KEY) return NextResponse.json({ ok: false, rule: 'not_configured' }, { status: 503 })
  const controller = new AbortController()
  const t = setTimeout(() => controller.abort(), 8000)
  try {
    const r = await fetch('https://api.liveavatar.com/v1/sessions/token', {
      method: 'POST', headers: { 'X-API-KEY': process.env.HEYGEN_API_KEY as string, 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'LITE', avatar_id: AVATAR_ID, is_sandbox: false }), signal: controller.signal, cache: 'no-store',
    })
    const j = await r.json().catch(() => ({}))
    const token = j?.data?.session_token || j?.data?.token || j?.session_token || j?.token
    if (!r.ok || !token) {
      console.error('[s2-avatar] token not minted', r.status, JSON.stringify(j).slice(0, 300))
      return NextResponse.json({ ok: false, rule: 'not_minted', status: r.status }, { status: 502 })
    }
    return NextResponse.json({ ok: true, token }, { headers: { 'cache-control': 'no-store' } })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'unreachable', message: (e as Error).name }, { status: 502 })
  } finally {
    clearTimeout(t)
  }
}
