export interface Traveller {
  id?: string
  relation: 'self' | 'partner' | 'child' | 'other'
  first_name?: string
  last_name?: string
  date_of_birth?: string
  dietary?: string[]
}

export interface Preference {
  key: string
  value: any
  source: 'explicit' | 'inferred' | 'post_trip' | 'corrected'
  confidence: number
  is_active: boolean
}

export interface User {
  id?: string
  display_name: string
  email?: string
  default_currency: string
  default_crypto?: string
  sasha_context?: string
  travellers: Traveller[]
  preferences: Preference[]
  past_trips?: any[]
  ota_affinity?: string[]
}

export interface ItineraryItem {
  id?: string
  type: 'flight' | 'hotel' | 'transfer' | 'activity' | 'car_hire'
  status: 'suggested' | 'selected' | 'held' | 'booked' | 'cancelled'
  display_name: string
  detail: any
  price_fiat: number
  price_currency: string
  is_refundable: boolean
  sasha_rationale?: string
  media?: any[]
}

export interface Itinerary {
  id?: string
  title: string
  ota_channel: string
  status: 'draft' | 'held' | 'confirmed' | 'active' | 'completed' | 'cancelled'
  depart_date?: string
  return_date?: string
  total_fiat: number
  items: ItineraryItem[]
  destination_summary?: any
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
}
