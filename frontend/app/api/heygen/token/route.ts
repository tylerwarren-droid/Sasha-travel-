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
        mode: 'LITE',
        avatar_id: process.env.NEXT_PUBLIC_HEYGEN_AVATAR_ID,
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
