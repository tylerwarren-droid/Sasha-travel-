/**
 * CR 16 · the PRODUCT TABS on project.kanoe.ai — RelocateMe, CampusMe, EspañaMe. Each is a brand (skin + opening mode)
 * over the SAME Sasha web chat: same account, same itinerary. Copy marked "[COPY: EU 150]" is a placeholder until EU 150's
 * copy lands in docs/business/. Every feature carries an honest label: live · click-through · concept.
 * ⛔ No Vietnam anywhere: these tabs pass their own presets and empty state.
 */
import type { DemoKind } from '../../(site)/content/types'

export type ProductKey = 'relocation' | 'campus' | 'espana'
export type Feature = { name: string; kind: DemoKind; note: string }
export type Brand = {
  key: ProductKey
  name: string                  // the brand, as the tab shows it
  mode: ProductKey              // the chat opens in this product's mode (products.web.web_turn)
  route: string                 // where the Sasha tab will mount it (the existing page, once the site hold lifts)
  hero: { kicker: string; headline: string; sub: string }
  features: Feature[]
  prompts: string[]             // the chat's preset prompts: this product's, never another's
  skin: { primary: string; accent: string; bg: string; ink: string; soft: string }
}

export const BRANDS: Record<ProductKey, Brand> = {
  relocation: {
    key: 'relocation', name: 'RelocateMe', mode: 'relocation', route: '/relocation',
    hero: { kicker: 'RelocateMe · Spain', headline: '[COPY: EU 150 — RelocateMe headline]',
            sub: '[COPY: EU 150 — one line: your residence file prepared and checked; you sign and lodge it]' },
    features: [
      { name: 'Your EX-01, filled and checked', kind: 'live', note: 'the real flow; the demo applicant is fictional' },
      { name: 'Your consulate’s own list and route (London and seven US consulates)', kind: 'live', note: 'read at source, dated' },
      { name: 'Flights, first nights and every deadline in one itinerary', kind: 'live', note: 'bookings are TEST bookings' },
    ],
    prompts: ['Start my residence application', 'Book my flights', 'What do I need to do this week?'],
    skin: { primary: '#b5442c', accent: '#e8a33d', bg: '#fbf4ec', ink: '#3a1c12', soft: '#f3e2d2' },
  },
  campus: {
    key: 'campus', name: 'CampusMe', mode: 'campus', route: '/campusme',
    hero: { kicker: 'CampusMe · US campus visits', headline: '[COPY: EU 150 — CampusMe headline]',
            sub: '[COPY: EU 150 — one line: real sessions from each school’s own calendar; you press Register]' },
    features: [
      { name: 'Real visit sessions from each school’s own calendar', kind: 'live', note: 'Yale and Penn, read live' },
      { name: 'The school’s form prepared; you press Register', kind: 'live', note: 'we never submit' },
      { name: 'The trip around the visits: flights, hotels, drive times', kind: 'live', note: 'bookings are TEST bookings' },
    ],
    prompts: ['Yale and Penn in November for my son', 'Plan the trip around the visits', 'What do I need to do this week?'],
    skin: { primary: '#1f3a6b', accent: '#c9a227', bg: '#f3f5fa', ink: '#0f1d36', soft: '#dfe6f3' },
  },
  espana: {
    key: 'espana', name: 'EspañaMe', mode: 'espana', route: '/spain-services',
    hero: { kicker: 'EspañaMe · Spain’s public services', headline: '[COPY: EU 150 — EspañaMe headline]',
            sub: '[COPY: EU 150 — one line: prepared for you; you press the button]' },
    features: [
      { name: 'A doctor: private clinic, the public service (SERMAS), or new in Madrid', kind: 'live',
        note: 'the SERMAS hand-over uses a fictional patient; no real health identifiers are kept' },
      { name: 'Padrón — registering at the town hall', kind: 'concept', note: 'designed, not built' },
      { name: 'Movistar — phone and internet at home', kind: 'concept', note: 'designed, not built; Movistar’s pages not read' },
    ],
    prompts: ['I need a doctor this week', 'I’m new in Madrid — my health card', 'Padrón'],
    skin: { primary: '#aa151b', accent: '#f1bf00', bg: '#fdf8ec', ink: '#3a0b0d', soft: '#f6e7c4' },
  },
}
