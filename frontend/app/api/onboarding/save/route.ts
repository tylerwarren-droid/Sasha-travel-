import { NextRequest } from 'next/server'
import { signedIn } from '@/lib/signed-in'

/** S-69 · the project comes from the environment (NEXT_PUBLIC_SUPABASE_URL) — never a ref written here, so moving
 *  Sasha to a new Supabase project is an env change, not a code change. Missing → nothing is saved, and it says so. */
const supabaseUrl = (): string | null => {
  const u = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? '').trim().replace(/\/+$/, '')
  return /^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(u) ? u : null
}

/**
 * S-58 · The service-role key is read from the environment ONLY — never written here, no fallback value. It used to
 * be hardcoded in this file (from 57119c3, 29 May 2026, in a public repository); that key is being rotated.
 * A legacy JWT key goes in both headers; a new `sb_secret_…` key only in `apikey` (Supabase refuses it as a Bearer).
 */
function serviceHeaders(): Record<string, string> | null {
  const key = (process.env.SUPABASE_SERVICE_ROLE_KEY ?? '').trim()
  if (!key) return null
  return key.startsWith('eyJ') ? { apikey: key, Authorization: `Bearer ${key}` } : { apikey: key }
}

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
  // S-62 sign-in gate (step 0, founder 1 Oct, Sasha 42): this route writes `clients` rows with the service-role key, so
  // nobody unsigned may reach it. A CTO drop that replaces this file fails the build (scripts/check-outcome-surfaces.mjs).
  if (!(await signedIn())) {
    return Response.json({ error: 'Sign in to save onboarding; nothing was saved', rule: 'sign_in_required' }, { status: 401 })
  }
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

  const base = supabaseUrl()
  if (!base) {
    console.error('Onboarding save refused: NEXT_PUBLIC_SUPABASE_URL is not set (or not a Supabase project URL) on this deployment')
    return Response.json({ error: 'Saving is not configured on this deployment (NEXT_PUBLIC_SUPABASE_URL is not set); nothing was saved' }, { status: 503 })
  }
  const auth = serviceHeaders()
  if (!auth) {
    console.error('Onboarding save refused: SUPABASE_SERVICE_ROLE_KEY is not set on this deployment')
    return Response.json({ error: 'Saving is not configured on this deployment (SUPABASE_SERVICE_ROLE_KEY is not set); nothing was saved' }, { status: 503 })
  }

  try {
    const res = await fetch(`${base}/rest/v1/clients`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...auth,
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
