'use client'

/**
 * Sasha 120 · YOU — the guest's own page in the main app: their bookings and every connection, in plain words. Each
 * block acts for the signed-in account alone (the server verifies it); nothing here is the founder's.
 */
import { SignedInGate } from '../components/SignedInGate'
import { WhoIsBooking } from '../components/SignedInLine'
import { MyBookings } from '../booking-helper/MyBookings'
import { WhatsAppLink } from '../booking-helper/WhatsAppLink'
import { CalendarConnect } from '../booking-helper/CalendarConnect'
import { MailboxConnect } from '../booking-helper/MailboxConnect'

export default function YouPage() {
  return (
    <SignedInGate>
      <main className="mx-auto my-6 max-w-2xl space-y-6 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
        <header className="space-y-1">
          <h1 className="text-xl font-semibold">You</h1>
          <WhoIsBooking />
          <p className="opacity-75">Your bookings, and what Sasha may use for you. Each one is yours alone, and you can switch it off here.</p>
        </header>
        <MyBookings />
        <WhatsAppLink />
        <CalendarConnect />
        <MailboxConnect />
        <section id="vault" className="space-y-1 rounded border p-3">
          <h2 className="font-semibold">My accounts (the vault)</h2>
          <p>The logins and membership numbers Sasha may use to book for you — each sealed on its own, every use listed.
            {' '}<a className="underline" href="/vault">Open my vault</a></p>
        </section>
      </main>
    </SignedInGate>
  )
}
