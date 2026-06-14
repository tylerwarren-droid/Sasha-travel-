import { NextResponse } from 'next/server'

// Never let a token request be cached — every session needs a fresh JWT.
export const dynamic = 'force-dynamic'

export async function GET() {
  if (!process.env.HEYGEN_API_KEY) {
    console.error('[token] HEYGEN_API_KEY is not set')
    return NextResponse.json({ error: 'Server not configured: missing LiveAvatar API key' }, { status: 500 })
  }

  // Bound the upstream call so a hung LiveAvatar API can't freeze the avatar's
  // loading state indefinitely — the client surfaces a retryable error instead.
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10000)
  try {
    const response = await fetch('https://api.liveavatar.com/v1/sessions/token', {
      method: 'POST',
      headers: {
        'X-API-KEY': process.env.HEYGEN_API_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        mode: 'FULL',
        avatar_id: 'ab0765ad-69de-41fb-9f8a-bd01c3c52d6f',
        avatar_persona: {
          context_id: '10b5933f-d54a-4305-9f88-333b628a1d09',
          voice_id: '62bbb4b2-bb26-4727-bc87-cfb2bd4e0cc8',
          language: 'en',
          speed: 0.8
        },
        is_sandbox: false
      }),
      signal: controller.signal,
    })
    const data = await response.json().catch(() => ({}))
    const token = data?.data?.session_token
    if (!token) {
      // Surface the upstream status/body so credit/auth/avatar errors are debuggable.
      console.error('[token] no session_token — upstream', response.status, JSON.stringify(data))
      return NextResponse.json({ error: 'No token from LiveAvatar', details: data }, { status: 502 })
    }
    return NextResponse.json({ token })
  } catch (error: any) {
    const msg = error?.name === 'AbortError'
      ? 'LiveAvatar token request timed out'
      : (error?.message || 'Token request failed')
    console.error('[token] error:', msg)
    return NextResponse.json({ error: msg }, { status: 504 })
  } finally {
    clearTimeout(timeout)
  }
}
