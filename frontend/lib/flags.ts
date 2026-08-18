// Payments are OFF for the current demo (client feedback 2026-08-11): Sasha takes
// reservations only — no Stripe, no "Book & Pay". Tapping Reserve (or saying "book it")
// records the reservation via POST /api/payments/reserve and mints a reference instantly.
// Set NEXT_PUBLIC_PAYMENTS_ENABLED=1 to restore the full Stripe checkout flow — the code
// paths are kept behind this flag, not deleted.
export const PAYMENTS_ENABLED = process.env.NEXT_PUBLIC_PAYMENTS_ENABLED === '1'
