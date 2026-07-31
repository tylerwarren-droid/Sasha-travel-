import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET() {
  if (!process.env.HEYGEN_API_KEY) {
    console.error('[token:phuquoc] HEYGEN_API_KEY is not set')
    return NextResponse.json({ error: 'Server not configured: missing LiveAvatar API key' }, { status: 500 })
  }

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
        avatar_id: '075abc67-2fae-4548-8ca9-b815fcbd34c7',
        avatar_persona: {
          context_id: 'f5721bed-ade9-4c26-9beb-7fd17d7d8211',
          voice_id: '62bbb4b2-bb26-4727-bc87-cfb2bd4e0cc8',
          language: 'en',
          // speed belongs inside voice_settings — a bare `speed` here was silently ignored
          voice_settings: { provider: 'elevenLabs', speed: 0.8 }
        },
        llm_configuration_id: '4267be4c-8959-443d-b682-36e7fff89b4d',
        is_sandbox: false
      }),
      signal: controller.signal,
    })
    const data = await response.json().catch(() => ({}))
    const token = data?.data?.session_token
    if (!token) {
      console.error('[token:phuquoc] no session_token — upstream', response.status, JSON.stringify(data))
      return NextResponse.json({ error: 'No token from LiveAvatar', details: data }, { status: 502 })
    }
    return NextResponse.json({ token })
  } catch (error: any) {
    const msg = error?.name === 'AbortError'
      ? 'LiveAvatar token request timed out'
      : (error?.message || 'Token request failed')
    console.error('[token:phuquoc] error:', msg)
    return NextResponse.json({ error: msg }, { status: 504 })
  } finally {
    clearTimeout(timeout)
  }
}
