'use client'
/**
 * Sasha 220 · "PAY HERE": the payment card inside the conversation — Stripe Embedded Checkout (TEST mode): a card, Apple Pay on
 * an iPhone's Safari, Google Pay where the browser has it. With no publishable key on the page (NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY,
 * pk_test_…), "Pay here" opens Stripe's own page on THIS device instead — never a dead end. Paid / booked are never said here:
 * the page hears it from Pacioli once Stripe's confirmation is recorded (the 'booked' event).
 */
import { useEffect, useRef, useState } from 'react'

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

export function PayHere({ clientSecret, url, totalEur, alreadyPaid }: { clientSecret?: string; url?: string; totalEur?: number; alreadyPaid?: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  const [phase, setPhase] = useState<'idle' | 'mounted' | 'done' | 'failed'>('idle')
  useEffect(() => {
    if (alreadyPaid || !PK || !clientSecret || !box.current) return
    let checkout: { destroy: () => void } | null = null
    let off = false
    loadStripe().then(async (S) => {
      if (off || !S || !box.current) { if (!S) setPhase('failed'); return }
      try {
        const c = await S(PK).initEmbeddedCheckout({ fetchClientSecret: async () => clientSecret, onComplete: () => setPhase('done') })
        if (off) { c.destroy(); return }
        checkout = c
        c.mount(box.current)
        setPhase('mounted')
      } catch { setPhase('failed') }
    })
    return () => { off = true; try { checkout?.destroy() } catch { /* already gone */ } }
  }, [clientSecret, alreadyPaid])

  const head = (k: string, h: string) => (
    <div className="lw-cardHd"><span className="lw-ci gold">💳</span><div className="lw-meta"><div className="lw-k">{k}</div><div className="lw-h">{h}</div></div></div>)
  if (alreadyPaid) return <div className="lw-card">{head('Already paid', 'Nothing more to pay — it’s booked once Stripe confirms')}</div>
  const total = typeof totalEur === 'number' ? `€${Math.round(totalEur).toLocaleString()} all in` : 'Your trip'
  return (
    <div className="lw-card">
      {head(phase === 'done' ? 'Payment received' : 'Pay here', phase === 'done' ? 'Confirming with Stripe — it shows as booked here when it’s recorded' : total)}
      <div className="lw-cardBody" style={{ display: 'block' }}>
        {PK && clientSecret && phase !== 'failed'
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
