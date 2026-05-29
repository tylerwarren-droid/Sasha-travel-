import { NextRequest } from 'next/server'

const SUPABASE_URL = 'https://xlqtveusyfpffaejegiq.supabase.co'
const SUPABASE_SERVICE_KEY =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhscXR2ZXVzeWZwZmZhZWplZ2lxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3ODc0Mzg0OCwiZXhwIjoyMDk0MzE5ODQ4fQ.Y9syb1MpOOZBjHhgXiMIMrrEeMbX_rdser57o9FseKU'

interface InventoryItem {
  name: string
  location: string
  commission: string
  tier: 'Platinum' | 'Gold' | 'Silver'
}

interface OnboardingData {
  business_name: string
  website_url: string
  destinations: string
  business_type: string
  currency: string
  contact_name: string
  contact_email: string
  contact_phone: string
  commission_model: string
  pathways: string[]
  persona_name: string
  tone: string
  languages: string[]
  destination_description: string
  selling_points: [string, string, string]
  best_time_to_visit: string
  never_discuss: string
  welcome_message: string
  inventory: {
    hotels: InventoryItem[]
    restaurants: InventoryItem[]
    spas: InventoryItem[]
    experiences: InventoryItem[]
  }
  inventory_urls: Record<string, string>
  agents: Record<string, boolean>
  slug: string
  completed_steps: number[]
}

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

function deriveAllowedDomains(websiteUrl: string, slug: string): string[] {
  const domains: string[] = []
  try {
    const url = new URL(websiteUrl.startsWith('http') ? websiteUrl : `https://${websiteUrl}`)
    domains.push(url.hostname)
  } catch {
    // ignore invalid URL
  }
  if (slug) {
    domains.push(`${slug}.sasha.kanoe.ai`)
  }
  return domains
}

function buildConfig(formData: OnboardingData): Record<string, unknown> {
  const hasHeyGen = formData.pathways.includes('heygen')
  const hasVoice = formData.pathways.includes('voice')

  return {
    persona_name: formData.persona_name || 'Sasha',
    persona_tagline: 'Your AI travel concierge',
    primary_color: '#0F6E56',
    allowed_currencies: formData.currency ? [formData.currency] : ['USD'],
    feature_flags: {
      voice: hasVoice,
      heygen: hasHeyGen,
      golf: formData.agents?.golf ?? true,
      restaurant: formData.agents?.restaurant ?? true,
      health: formData.agents?.health ?? true,
      beauty: formData.agents?.beauty ?? true,
      petcare: formData.agents?.petcare ?? true,
      booking: formData.agents?.booking ?? true,
      scuba: formData.agents?.scuba ?? false,
      surf: formData.agents?.surf ?? false,
      transfers: formData.agents?.transfers ?? false,
    },
    onboarding: {
      business_name: formData.business_name,
      website_url: formData.website_url,
      destinations: formData.destinations,
      business_type: formData.business_type,
      currency: formData.currency,
      contact_name: formData.contact_name,
      contact_email: formData.contact_email,
      contact_phone: formData.contact_phone,
      commission_model: formData.commission_model,
      pathways: formData.pathways,
      tone: formData.tone,
      languages: formData.languages,
      destination_description: formData.destination_description,
      selling_points: formData.selling_points,
      best_time_to_visit: formData.best_time_to_visit,
      never_discuss: formData.never_discuss,
      completed_steps: formData.completed_steps,
      inventory_urls: formData.inventory_urls,
    },
    welcome_message: formData.welcome_message,
    inventory: formData.inventory,
  }
}

export async function POST(request: NextRequest) {
  let body: { formData: OnboardingData; goLive?: boolean }
  try {
    body = await request.json() as { formData: OnboardingData; goLive?: boolean }
  } catch {
    return Response.json({ error: 'Invalid JSON body' }, { status: 400 })
  }

  const { formData, goLive } = body

  if (!formData) {
    return Response.json({ error: 'formData is required' }, { status: 400 })
  }

  const slug = formData.slug || slugify(formData.business_name || 'untitled')
  const allowedDomains = deriveAllowedDomains(formData.website_url || '', slug)
  const config = buildConfig(formData)

  const payload = {
    slug,
    display_name: formData.business_name || slug,
    allowed_domains: allowedDomains,
    config,
    is_active: goLive === true,
  }

  try {
    const res = await fetch(`${SUPABASE_URL}/rest/v1/clients`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        apikey: SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${SUPABASE_SERVICE_KEY}`,
        Prefer: 'resolution=merge-duplicates',
      },
      body: JSON.stringify(payload),
    })

    if (!res.ok) {
      const errorText = await res.text()
      console.error('Supabase upsert error:', res.status, errorText)
      return Response.json(
        { error: 'Failed to save to database', details: errorText },
        { status: 500 }
      )
    }

    return Response.json({
      slug,
      url: `https://sasha.kanoe.ai/${slug}`,
    })
  } catch (err) {
    console.error('Onboarding save error:', err)
    return Response.json({ error: 'Internal server error' }, { status: 500 })
  }
}
