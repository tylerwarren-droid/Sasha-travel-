import type { Tab } from './types'

// kanoe-site-scope.md §11 (EU 136), verbatim.
export const sasha: Tab = {
  route: '/sasha',
  title: 'Sasha — Kanoe',
  description: 'Book anything in Madrid, directly with the venue, in the venue\'s language, with proof.',
  headline: 'Book anything in Madrid, directly with the venue, in the venue\'s language, with proof.',
  lines: [
    { status: 'proven', evidence: 'booking_signer: ladder.py, calls.py (the AI disclosure first), form_rung.py, ladder_routes.py (email), guest_whatsapp.py',
      text: 'Ask once. Sasha finds the place, reads you exactly what she\'ll say, and books only on your yes, by phone (she says she\'s an AI), email, the venue\'s own form, or WhatsApp.' },
    { status: 'proven', evidence: 'booking_signer: receipt.py, guest_receipt.py, cancel_routes.py ("cancelled" only on their words), recap.py',
      text: 'You get the venue\'s own confirmation, a receipt, and "cancelled" only when the venue says so. Unclear is never shown as booked.' },
    { status: 'proven', evidence: 'booking_signer: wa_agent.py (the one brain on WhatsApp), guest_whatsapp.py (cancel), proactive.py (time to leave)',
      text: 'On WhatsApp: cards with each venue\'s own photos, cancel by message, time to leave.' },
  ],
  statusLine: 'Live in closed beta in Madrid. WhatsApp runs on Twilio\'s sandbox until Meta verifies us. Our confirmation rate isn\'t published yet: the sample is too small.',
  demo: { kind: 'live', sentence: 'Live: the real product. Our test venue is ours and says so.',
    links: [
      { href: '/sign-in', label: 'Sign in to book (invite-only)' },
      { href: 'https://sasha-travel-production.up.railway.app/api/booking/test-venue/plain', label: 'Our test venue (ours — not a real restaurant)', external: true },
    ] },
}
