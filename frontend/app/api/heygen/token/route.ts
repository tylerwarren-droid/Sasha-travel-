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
    const text = await response.text()
    console.log('HeyGen raw response:', text)
    try {
      const data = JSON.parse(text)
      if (!data.data?.token) {
        return NextResponse.json({ error: 'No token', details: data }, { status: 500 })
      }
      return NextResponse.json({ token: data.data.token })
    } catch {
      return NextResponse.json({ error: 'HeyGen returned non-JSON', raw: text.slice(0, 200) }, { status: 500 })
    }
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
