/**
 * Sasha 303 · THE ONE place a LiveAvatar (HeyGen) session token is minted — SERVER ONLY. Its one caller is
 * app/api/s2-avatar/token/route.ts, and only after the gate (backend app/avatar_gate.py) said yes; the token then goes to the gate
 * at once, which holds it and closes the session. Pinned: scripts/avatar-gate-303.test.mjs (no other file mints one).
 */
const AVATAR_ID = 'ab0765ad-69de-41fb-9f8a-bd01c3c52d6f'   // /s2's face (LITE: her lips, her own voice)

export async function mintSession(): Promise<{ token: string; sessionId: string | null } | { error: string; status: number }> {
  const key = process.env.HEYGEN_API_KEY
  if (!key) return { error: 'not_configured', status: 503 }
  const controller = new AbortController()
  const t = setTimeout(() => controller.abort(), 8000)
  try {
    const r = await fetch('https://api.liveavatar.com/v1/sessions/token', {
      method: 'POST', headers: { 'X-API-KEY': key, 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'LITE', avatar_id: AVATAR_ID, is_sandbox: false }), signal: controller.signal, cache: 'no-store',
    })
    const j = await r.json().catch(() => ({}))
    const token = j?.data?.session_token || j?.data?.token || j?.session_token || j?.token
    if (!r.ok || !token) {
      console.error('[avatar-mint] token not minted', r.status)
      return { error: 'not_minted', status: 502 }
    }
    return { token, sessionId: j?.data?.session_id || j?.session_id || null }
  } catch (e) {
    return { error: (e as Error).name === 'AbortError' ? 'timeout' : 'unreachable', status: 502 }
  } finally {
    clearTimeout(t)
  }
}
