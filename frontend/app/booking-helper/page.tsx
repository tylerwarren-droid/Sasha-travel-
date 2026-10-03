'use client'

/**
 * Sasha 120 · OPS — the founder's page, not a guest's. Guests book in the chat or on WhatsApp, and manage what Sasha may
 * use for them on "You" (/you); no guest surface links here. What stays: the long-form rungs for checking a venue by
 * hand (Ladder, PhoneCall — a call goes only to a venue on the server's list), and where the rest of the ops live.
 *
 * Sasha 88 · the Restaurante Psi form-helper block is REMOVED (it promised a booking it never made).
 */
import { PhoneCall } from './PhoneCall'
import { Ladder } from './Ladder'
import { FounderGate } from './FounderGate'
import { InviteGuest } from './InviteGuest'
import { DemoControls } from './DemoControls'

/** The details pre-filled while testing; every field stays editable. */
const DEMO_PROFILE = { name: 'Jon Peters', email: 'jon@kanoe.ai', phone: '+44 20 7946 0123' }

export default function OpsPage() {
  return (
    // S-41 · founder only: signed out, the page is a passphrase field and nothing else
    <FounderGate>
    {/* ⚠ The site's global style is DARK — this page carries its own light surface so every field is legible. */}
    <main className="mx-auto my-6 max-w-2xl space-y-6 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Ops — founder only</h1>
        <p className="opacity-75">Guests never see this page. Your own connections (WhatsApp, Calendar, Gmail, reminders, the vault) are on <a className="underline" href="/you">You</a>.</p>
        <ul className="list-disc pl-5">
          <li><a className="underline" href="https://sasha-travel-production.up.railway.app/api/booking/test-venue/plain" target="_blank" rel="noopener noreferrer">The test venue</a> — ours, not a real restaurant: its form takes Sasha&rsquo;s test bookings.</li>
          <li><a className="underline" href="https://sasha-travel-production.up.railway.app/api/booking/health" target="_blank" rel="noopener noreferrer">Server health</a> — calls on or off, the caps, the vault, Calendar, Gmail and reminder loops.</li>
          <li>Calls: the call panel below; a guest&rsquo;s calls are off until you list their account in SASHA_CALLS_ACCOUNTS.</li>
        </ul>
      </header>
      <DemoControls />
      <InviteGuest />
      <Ladder defaults={DEMO_PROFILE} />
      <PhoneCall defaults={DEMO_PROFILE} />
    </main>
    </FounderGate>
  )
}
