import { NextResponse } from 'next/server'

export async function GET() {
  try {
    const response = await fetch('https://api.heygen.com/v1/live_avatar.create_session_token', {
      method: 'POST',
      headers: {
        'x-api-key': process.env.HEYGEN_API_KEY!,
        'Content-Type': 'application/json',
      },
    })
    const data = await response.json()
    console.log('HeyGen response:', JSON.stringify(data))
    if (!data.data?.token) {
      return NextResponse.json({ error: 'No token returned', details: data }, { status: 500 })
    }
    return NextResponse.json({ token: data.data.token })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
