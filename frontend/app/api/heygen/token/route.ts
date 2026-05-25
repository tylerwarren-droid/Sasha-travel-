import { NextResponse } from 'next/server'
export async function GET() {
  try {
    const response = await fetch('https://api.liveavatar.com/v1/sessions/token', {
      method: 'POST',
      headers: {
        'X-API-KEY': process.env.HEYGEN_API_KEY!,
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
        llm_configuration_id: '4267be4c-8959-443d-b682-36e7fff89b4d',
        is_sandbox: false
      }),
    })
    const data = await response.json()
    console.log('LiveAvatar response:', JSON.stringify(data))
    const token = data.data?.session_token
    if (!token) {
      return NextResponse.json({ error: 'No token', details: data }, { status: 500 })
    }
    return NextResponse.json({ token })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
