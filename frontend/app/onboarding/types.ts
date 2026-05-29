export interface InventoryItem {
  name: string
  location: string
  commission: string
  tier: 'Platinum' | 'Gold' | 'Silver'
}

export interface OnboardingData {
  // Step 1
  business_name: string
  website_url: string
  destinations: string
  business_type: string
  currency: string
  contact_name: string
  contact_email: string
  contact_phone: string
  commission_model: string
  // Step 2
  pathways: string[]
  // Step 3
  persona_name: string
  tone: string
  languages: string[]
  destination_description: string
  selling_points: [string, string, string]
  best_time_to_visit: string
  never_discuss: string
  welcome_message: string
  // Step 4
  inventory: {
    hotels: InventoryItem[]
    restaurants: InventoryItem[]
    spas: InventoryItem[]
    experiences: InventoryItem[]
  }
  inventory_urls: Record<string, string>
  // Step 5
  agents: Record<string, boolean>
  // Meta
  slug: string
  completed_steps: number[]
}

export const defaultOnboardingData: OnboardingData = {
  business_name: '',
  website_url: '',
  destinations: '',
  business_type: '',
  currency: 'USD',
  contact_name: '',
  contact_email: '',
  contact_phone: '',
  commission_model: '',
  pathways: [],
  persona_name: 'Sasha',
  tone: '',
  languages: ['English'],
  destination_description: '',
  selling_points: ['', '', ''],
  best_time_to_visit: '',
  never_discuss: '',
  welcome_message: '',
  inventory: {
    hotels: [],
    restaurants: [],
    spas: [],
    experiences: [],
  },
  inventory_urls: {},
  agents: {
    restaurant: true,
    health: true,
    beauty: true,
    golf: true,
    petcare: true,
    booking: true,
    scuba: false,
    surf: false,
    transfers: false,
  },
  slug: '',
  completed_steps: [],
}
