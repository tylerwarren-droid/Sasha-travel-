import { NextResponse } from 'next/server'

export async function GET() {
  try {
    const response = await fetch('https://api.heygen.com/v1/streaming.create_token', {
      method: 'POST',
      headers: {
        'x-api-key': process.env.HEYGEN_API_KEY!,
        'Content-Type': 'application/json',
      },
    })
    const data = await response.json()
    return NextResponse.json({ token: data.data?.token })
  } catch (error) {
    return NextResponse.json({ error: 'Failed to get token' }, { status: 500 })
  }
}
