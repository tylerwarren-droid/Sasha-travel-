'use client'

/**
 * CR 16 · Sasha's OWN web chat (components/SashaChat — reused, never forked; Sasha 140's streaming untouched), opened in
 * this product's mode: `productMode` goes to the conductor on the first turn (products.web.web_turn), the product's
 * buttons come back as quick replies. The brand changes only the skin and the opening mode.
 *
 * `productMode` / `skinClassName` are the Sasha tab's props (CR 16 a–c, agreed 4 Oct); until they land in SashaChat
 * they are passed through untyped, so this file builds today and works the moment they exist.
 */
import SashaChat from '../SashaChat'
import type { User } from '@/types'
import type { Brand } from './brands'
import b from './brand.module.css'

// a neutral guest: no name, no Vietnam, no preferences — the signed-in account (S-62) is what the turn acts for
const NEUTRAL_USER: User = { display_name: '', default_currency: 'EUR', travellers: [], preferences: [] }

export default function ProductChat({ brand }: { brand: Brand }) {
  const cr16 = { productMode: brand.mode, skinClassName: b.chatBody } as Record<string, unknown>   // CR 16 a–c props
  return (
    <section className={b.chatWrap} aria-label={`Sasha — ${brand.name}`}>
      <div className={b.chatHead}>
        <span>Sasha · {brand.name}</span>
        <small>Same account, same itinerary as everywhere you use Sasha</small>
      </div>
      <div className={b.chatBody}>
        <SashaChat
          user={NEUTRAL_USER}
          hideTabs
          presetPrompts={brand.prompts}
          emptyState={<div className={b.empty}><b>{brand.name}</b> — opening in its own mode. Ask anything else at any time: a booking, a flight, your plans.</div>}
          {...cr16}
        />
      </div>
    </section>
  )
}
