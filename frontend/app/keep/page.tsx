'use client'

/**
 * CR 63 · THE KEEP — where your numbers and codes live, on your phone. Sasha (the AI) only ever sees a mask ("Passport ES
 * ••••456"); code fills the real value into a booking at the moment of use, after your yes for a document. Door codes, Wi-Fi
 * and booking references are only ever shown to YOU, here. Card numbers, one-time codes and passwords are never kept.
 * Values go from this form straight to the server, which seals them under your own key; nothing here logs or keeps them.
 *
 * Sasha 235 · the screen itself lives in ./KeepScreen (the same one /s2's "My Keep" tab shows), with each item's uses.
 */
import { SignedInGate } from '../components/SignedInGate'
import { KeepScreen } from './KeepScreen'

export default function KeepPage() {
  return (
    <SignedInGate>
      <main className="mx-auto min-h-screen max-w-md bg-white pb-10 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
        <h1 className="px-4 pb-1 pt-6 text-2xl font-bold">Your Keep</h1>
        <p className="px-4 pb-3 text-sm opacity-60">Sasha never sees these — only “Passport ES ••••456”. They’re filled in where needed, at that moment, after your yes.</p>
        <KeepScreen />
      </main>
    </SignedInGate>
  )
}
