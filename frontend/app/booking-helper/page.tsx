'use client'

/**
 * The booking page — founder only. The live rungs: read a venue and book it by phone or email (Ladder), and a call to
 * a venue on the server's list (PhoneCall). Bookings are normally made in Sasha's chat; this page is the long form.
 *
 * Sasha 88 · the Restaurante Psi form-helper block (S-25: a dry run through a Chrome extension, steps 1–4, the Psi
 * reservation and the helper's log) is REMOVED. It promised a booking it never made — a dry run stops before sending —
 * and it sat above the real rungs. The server's form routes are unchanged; only this page no longer offers them.
 */
import { PhoneCall } from './PhoneCall'
import { Ladder } from './Ladder'
import { FounderGate } from './FounderGate'

/** The details pre-filled while testing; every field stays editable. */
const DEMO_PROFILE = { name: 'Jon Peters', email: 'jon@kanoe.ai', phone: '+44 20 7946 0123' }

export default function BookingHelperPage() {
  return (
    // S-41 · founder only: signed out, the page is a passphrase field and nothing else
    <FounderGate>
    {/* ⚠ The site's global style is DARK and inputs inherit that text colour onto the browser's white field — this page
        carries its own light surface so every field is legible whatever the site's theme. */}
    <main className="mx-auto my-6 max-w-2xl space-y-6 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Book with Sasha</h1>
        <p className="opacity-75">The usual way is to ask Sasha in the chat. Here: read a venue, then book it by phone or email — every call and email is read back to you before anything is sent.</p>
      </header>
      <Ladder defaults={DEMO_PROFILE} />
      <PhoneCall defaults={DEMO_PROFILE} />
    </main>
    </FounderGate>
  )
}
