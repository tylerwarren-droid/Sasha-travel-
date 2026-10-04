/**
 * CR 16 · the PRODUCT TABS on project.kanoe.ai — RelocateMe, CampusMe, EspañaMe. Each is a brand (skin + opening mode)
 * over the SAME Sasha web chat: same account, same itinerary. Copy: EU 150, docs/business/product-tabs-copy.md (4 Oct
 * 2026), verbatim. Marks: ✅ built and rehearsed (cited) · ○ concept. The status line is always shown, in the tab's colours.
 * ⛔ No Vietnam anywhere. ⛔ No flags, crests, university colours or government styling (EU's colour notes).
 * The opening line Sasha says in each mode is in backend/products/web.py (OPENING), from the same copy.
 */
import type { DemoKind } from '../../(site)/content/types'

export type ProductKey = 'relocation' | 'campus' | 'espana'
export type Line = { mark: 'built' | 'concept'; text: string; cite: string }
export type Brand = {
  key: ProductKey
  name: string                  // the brand, as the tab shows it
  mode: ProductKey              // the chat opens in this product's mode (products.web.web_turn)
  route: string                 // where the Sasha tab will mount it (the existing page, once the site hold lifts)
  kind: DemoKind                // the tab's overall label
  badge?: string                // EspañaMe: the CONCEPT badge at the TOP of the tab
  hero: string
  lines: Line[]                 // three, or four where EU added a concept line (EU 153)
  statusLine: string
  prompts: string[]             // "Try saying" — this product's, never another's
  skin: { primary: string; accent: string; bg: string; ink: string; soft: string }
}

export const BRANDS: Record<ProductKey, Brand> = {
  relocation: {
    key: 'relocation', name: 'RelocateMe', mode: 'relocation', route: '/relocation', kind: 'live',
    hero: 'Moving to Spain? I’ll handle the paperwork and the trip.',
    lines: [
      { mark: 'built', cite: 'CR 1–2: 30cabe1, d632f90',
        text: 'Send a photo of your passport. I read it, check it against its own check digits, and read every value back for your yes.' },
      { mark: 'built', cite: 'CR 1–2; CR 12: US consulates, 7 of 8 read (a22fcad)',
        text: 'I prepare Spain’s official EX-01 from your own words, check it field by field, and hand it to you to sign. I never sign it and never file it.' },
      { mark: 'built', cite: 'CR 13: the trip, rehearsed 41/41',
        text: 'Then the trip: your flights, your first nights near your new address, and one itinerary with every booking and every deadline.' },
      { mark: 'concept', cite: 'EU 153: moved here from EspañaMe; no provider\u2019s pages read',
        text: 'Next: your phone line and utilities set up before you arrive.' },
    ],
    statusLine: 'Working today on WhatsApp in our test setup, for a first application lodged from the UK or the US. Flights and hotels shown here are test bookings. Renewals and family applications aren’t built yet.',
    prompts: ['I’m moving to Madrid from London in March', 'book my flights', 'Here’s my passport'],
    skin: { primary: '#1E4E8C', accent: '#5B9BD5', bg: '#F3F7FC', ink: '#13263f', soft: '#d9e4f2' },
  },
  campus: {
    key: 'campus', name: 'CampusMe', mode: 'campus', route: '/campusme', kind: 'live',
    hero: 'Plan the campus tour: visits, flights, hotels.',
    lines: [
      { mark: 'built', cite: 'CR 1, 8106303',
        text: 'I read each university’s own visit calendar, live, and show you the real sessions and spaces left, or tell you plainly when a month isn’t published yet.' },
      { mark: 'built', cite: 'CR 1, 8106303',
        text: 'One yes and I prepare the school’s own registration from your saved details. I stop before the Register button: you press it.' },
      { mark: 'built', cite: 'CR 13',
        text: 'Then the trip around the visits: flights, a hotel near each campus, and the drive between them checked.' },
    ],
    statusLine: 'Working today on WhatsApp in our test setup, read-only on the universities’ sites (Yale and Penn proven). Nothing is ever submitted to a university for you. Flights and hotels shown here are test bookings. Drive times are checked; train times aren’t yet.',
    prompts: ['campus visits at Yale and Penn in November for my son', 'plan the trip around the visits', 'what about April?'],
    skin: { primary: '#7A1F2B', accent: '#C9A227', bg: '#FAF7F0', ink: '#1F2F4A', soft: '#eadfcb' },
  },
  espana: {
    key: 'espana', name: 'EspañaMe', mode: 'espana', route: '/spain-services', kind: 'concept',
    badge: 'CONCEPT: designed, with one part working in our test setup.',
    hero: 'Spain’s public services, made simple.',
    lines: [
      { mark: 'built', cite: 'CR 4: e621e03, rehearsals 46/46',
        text: 'New in Madrid? I walk you through it in order — padrón, social security, health card, family doctor — each step from its official page.' },
      { mark: 'built', cite: 'S-77’s line; CR 4',
        text: 'I get everything ready for your appointment — the official page, the details to copy — and you press. I never sign in to a public service for you, and never book it for you.' },
      { mark: 'concept', cite: 'EU 153: the padrón, Cl@ve / digital certificate, social security and tax, the DGT and education are concepts, unstudied',
        text: 'Next: the padrón, Cl@ve and your digital certificate, social security and tax, the DGT, and schools — each studied at its official source before anything is built.' },
    ],
    statusLine: 'A concept. The health steps work today in our test setup: a private clinic booked by phone, and public appointments prepared for you to press. Nothing stores your health details until our data-protection assessment is done. Everything else here is designed, not built.',
    prompts: ['I need a doctor this week', 'I’ve just moved to Madrid — what do I do first?', 'how do I get my health card?'],
    skin: { primary: '#B5121B', accent: '#E8B321', bg: '#FFF8EC', ink: '#2A1A12', soft: '#f3e2c4' },
  },
}
