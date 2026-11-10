'use client'
/**
 * Sasha 220 · "PAY HERE": the payment card inside the conversation — Stripe Embedded Checkout (TEST mode): a card, Apple Pay on
 * an iPhone's Safari, Google Pay where the browser has it. With no publishable key on the page (NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY,
 * pk_test_…), "Pay here" opens Stripe's own page on THIS device instead — never a dead end. Paid / booked are never said here:
 * the page hears it from Pacioli once Stripe's confirmation is recorded (the 'booked' event).
 */
import { useEffect, useRef, useState } from 'react'
import { eur as euros } from '@/lib/money'   // Sasha 349 · one way to say money

const PK = (process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? '').trim()

type StripeJs = { initEmbeddedCheckout: (o: { fetchClientSecret: () => Promise<string>; onComplete?: () => void }) => Promise<{ mount: (el: HTMLElement) => void; destroy: () => void }> }

function loadStripe(): Promise<((pk: string) => StripeJs) | null> {
  const w = window as unknown as { Stripe?: (pk: string) => StripeJs }
  if (w.Stripe) return Promise.resolve(w.Stripe)
  return new Promise((res) => {
    const s = document.createElement('script')
    s.src = 'https://js.stripe.com/v3/'
    s.onload = () => res(w.Stripe ?? null)
    s.onerror = () => res(null)
    document.head.appendChild(s)
  })
}

/** Sasha 364 · `result`: the booking's own outcome in Sasha's words (the settled event's) — once Stripe's checkout completes it is
 *  REMOVED and the card shows Sasha's state, never Stripe's "You're all done here" (Tyler's dry run, 9 Nov). */
export function PayHere({ clientSecret, url, totalEur, alreadyPaid, result }: { clientSecret?: string; url?: string; totalEur?: number; alreadyPaid?: boolean; result?: string }) {
  const box = useRef<HTMLDivElement>(null)
  const live = useRef<{ destroy: () => void } | null>(null)
  const [phase, setPhase] = useState<'idle' | 'mounted' | 'done' | 'failed'>('idle')
  useEffect(() => {
    if (alreadyPaid || !PK || !clientSecret || !box.current) return
    let checkout: { destroy: () => void } | null = null
    let off = false
    loadStripe().then(async (S) => {
      if (off || !S || !box.current) { if (!S) setPhase('failed'); return }
      try {
        const c = await S(PK).initEmbeddedCheckout({ fetchClientSecret: async () => clientSecret,
          onComplete: () => { try { live.current?.destroy() } catch { /* already gone */ } live.current = null; setPhase('done') } })
        if (off) { c.destroy(); return }
        checkout = c
        live.current = c
        c.mount(box.current)
        setPhase('mounted')
      } catch { setPhase('failed') }
    })
    return () => { off = true; try { checkout?.destroy() } catch { /* already gone */ } }
  }, [clientSecret, alreadyPaid])

  const head = (k: string, h: string) => (
    <div className="lw-cardHd"><span className="lw-ci gold">💳</span><div className="lw-meta"><div className="lw-k">{k}</div><div className="lw-h">{h}</div></div></div>)
  if (result) return <div className="lw-card" data-pay-result>{head(alreadyPaid ? 'Booked' : 'Not booked', result)}</div>
  if (alreadyPaid) return <div className="lw-card">{head('Paid', 'Nothing more to pay')}</div>
  const total = typeof totalEur === 'number' ? `${euros(totalEur)} all in` : 'Your trip'
  return (
    <div className="lw-card">
      {head(phase === 'done' ? 'Booking it now' : 'Pay here', phase === 'done' ? 'Your card is only held — it’s taken when the booking is confirmed' : total)}
      <div className="lw-cardBody" style={{ display: phase === 'done' ? 'none' : 'block' }}>
        {PK && clientSecret && phase !== 'failed' && phase !== 'done'
          ? <div ref={box} style={{ minHeight: phase === 'mounted' ? 0 : 120 }} data-testid="pay-embedded" />
          : url
            ? <a className="lw-callink" href={url} target="_blank" rel="noreferrer" data-testid="pay-here-link"
                style={{ display: 'inline-block', padding: '10px 16px', borderRadius: 999, background: '#E8B923', color: '#111', fontWeight: 700, textDecoration: 'none' }}>
                Pay here →</a>
            : <div className="o2">The payment card couldn’t load — say “send it to my phone” and I’ll move this same payment there.</div>}
      </div>
    </div>
  )
}
