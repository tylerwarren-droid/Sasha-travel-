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
        avatar_id: 'dd73ea75-1218-4ef3-92ce-606d5f7fbc0a',
        avatar_persona: {
          context_id: '5b9dba8a-aa31-11f0-a6ee-066a7fa2e369',
          voice_id: 'c2527536-6d1f-4412-a643-53a3497dada9',
          language: 'en'
        },
        is_sandbox: true
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
