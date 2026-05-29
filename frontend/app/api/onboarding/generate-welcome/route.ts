import { NextRequest } from 'next/server'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface GenerateWelcomeRequest {
  business_name: string
  persona_name: string
  destinations: string
  description: string
}

export async function POST(request: NextRequest) {
  let body: GenerateWelcomeRequest
  try {
    body = await request.json() as GenerateWelcomeRequest
  } catch {
    return Response.json({ error: 'Invalid JSON body' }, { status: 400 })
  }

  const { business_name, persona_name, destinations, description } = body

  const prompt = `Generate a warm, professional welcome message for ${persona_name || 'Sasha'}, the AI travel concierge for ${business_name || 'our travel company'}. ${destinations ? `They specialise in ${destinations}.` : ''} ${description ? `About the property/destinations: ${description}` : ''} The message should be 2-3 sentences, welcoming and inviting. Do not include quotation marks. Return only the welcome message text.`

  try {
    const res = await fetch(`${API_BASE_URL}/api/agents/conductor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: prompt }),
    })

    if (!res.ok) {
      const errorText = await res.text()
      console.error('Conductor error:', res.status, errorText)
      return Response.json(
        { error: 'Failed to generate welcome message' },
        { status: 500 }
      )
    }

    const data = await res.json() as { response?: string; message?: string; content?: string; text?: string }
    const welcome_message =
      data.response || data.message || data.content || data.text || ''

    return Response.json({ welcome_message })
  } catch (err) {
    console.error('Generate welcome error:', err)
    return Response.json({ error: 'Internal server error' }, { status: 500 })
  }
}
