import { NextResponse } from 'next/server'
import { CURRENT_USER } from '../../../../lib/currentUser'

// Never let a token request be cached — every session needs a fresh JWT.
export const dynamic = 'force-dynamic'

const AVATAR_ID = 'ab0765ad-69de-41fb-9f8a-bd01c3c52d6f'
const CONTEXT_ID = '10b5933f-d54a-4305-9f88-333b628a1d09'
const VOICE_ID = '62bbb4b2-bb26-4727-bc87-cfb2bd4e0cc8'
const SUPPORTED_LANGS = new Set(['en', 'vi', 'ko', 'zh', 'ja', 'fr', 'es', 'de', 'hi'])

async function mintToken(body: any) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10000)
  try {
    const res = await fetch('https://api.liveavatar.com/v1/sessions/token', {
      method: 'POST',
      headers: { 'X-API-KEY': process.env.HEYGEN_API_KEY as string, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    const data = await res.json().catch(() => ({}))
    return { ok: res.ok, status: res.status, data }
  } finally {
    clearTimeout(timeout)
  }
}

export async function GET(request: Request) {
  if (!process.env.HEYGEN_API_KEY) {
    console.error('[token] HEYGEN_API_KEY is not set')
    return NextResponse.json({ error: 'Server not configured: missing LiveAvatar API key' }, { status: 500 })
  }

  const url = new URL(request.url)
  const langParam = (url.searchParams.get('lang') || 'en').toLowerCase()
  const lang = SUPPORTED_LANGS.has(langParam) ? langParam : 'en'
  const prevSession = url.searchParams.get('prev_session') || ''

  const base: any = {
    mode: 'FULL',
    avatar_id: AVATAR_ID,
    // `speed` lives INSIDE voice_settings (per-provider union) — a bare `speed` on
    // avatar_persona is not in AvatarPersonaSchema and was silently ignored, so the
    // avatar spoke at default speed. Verified live: this shape mints (code 1000).
    avatar_persona: {
      context_id: CONTEXT_ID, voice_id: VOICE_ID, language: lang,
      voice_settings: { provider: 'elevenLabs', speed: 0.8 },
    },
    // Personalize the avatar's opening line with the (currently hardcoded) user's name.
    // For the spoken opening to say it, the LiveAvatar context's opening_text must reference
    // ${first_name} (e.g. "Hello ${first_name}! I'm Sasha..."). If it doesn't, this is a
    // harmless no-op and Sasha still greets by name on her first conductor-driven reply.
    dynamic_variables: { first_name: CURRENT_USER.firstName, full_name: CURRENT_USER.displayName },
    is_sandbox: false,
  }

  try {
    // Cross-session memory (LiveAvatar Session Memory API): if we have the prior session id,
    // ask the avatar to carry memory forward so a returning guest is remembered. If the
    // account/session can't resolve it, retry cleanly WITHOUT memory so the session still starts.
    let result
    if (prevSession) {
      result = await mintToken({ ...base, memory: { prev_session_id: prevSession } })
      if (!result.ok) {
        console.warn('[token] memory attach failed, retrying without memory:', result.status)
        result = await mintToken(base)
      }
    } else {
      result = await mintToken(base)
    }

    const token = result.data?.data?.session_token
    if (!token) {
      console.error('[token] no session_token — upstream', result.status, JSON.stringify(result.data))
      return NextResponse.json({ error: 'No token from LiveAvatar', details: result.data }, { status: 502 })
    }
    return NextResponse.json({ token })
  } catch (error: any) {
    const msg = error?.name === 'AbortError' ? 'LiveAvatar token request timed out' : (error?.message || 'Token request failed')
    console.error('[token] error:', msg)
    return NextResponse.json({ error: msg }, { status: 504 })
  }
}
