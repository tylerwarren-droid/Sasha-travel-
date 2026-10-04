'use client'

/** Sasha 144 · THE CALL AND BOOKING LOG — founder only (the same gate as the ops page), not linked from any guest surface. */
import { FounderGate } from '../FounderGate'
import { CallLog } from '../CallLog'

export default function LogPage() {
  return (
    <FounderGate>
      <main className="mx-auto my-6 max-w-6xl space-y-4 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
        <header className="space-y-1">
          <h1 className="text-xl font-semibold">Call and booking log — founder only</h1>
          <p className="opacity-75">Every call Sasha placed (test-line calls marked TEST) and every booking, from the records. For a venue&rsquo;s
            dispute: search its name or a reference, then open Bland&rsquo;s own record of the call. <a className="underline" href="/booking-helper">← Ops</a></p>
        </header>
        <CallLog />
      </main>
    </FounderGate>
  )
}
