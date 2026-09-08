// Legacy switch from the Aug-11 reservation-only demo. Since 2026-09-05 the booking flow is
// the saved-card handshake regardless of this flag: "book it" (spoken) or a Reserve tap makes
// Sasha ask "saved card ending 1003, or a different card?"; the saved card completes in-app
// via POST /api/payments/reserve (no Stripe), a different card opens Stripe Checkout (which
// needs STRIPE_SECRET_KEY on the backend). This flag now only affects the legacy
// await_payment / verify wording paths and can stay unset.
export const PAYMENTS_ENABLED = process.env.NEXT_PUBLIC_PAYMENTS_ENABLED === '1'

// The saved card on file for the demo profile. A tap on Reserve / Book routes through Sasha's
// spoken "saved card ending 1003, or a different card?" question exactly like a verbal "book
// it", so the frontend needs the digits to phrase the question itself (the backend keys the
// guest's answer on the phrase "ending in <last4>" in Sasha's last line). Keep in step with the
// backend's SASHA_SAVED_CARD_LAST4.
export const SAVED_CARD_LAST4 = process.env.NEXT_PUBLIC_SAVED_CARD_LAST4 || '1003'
