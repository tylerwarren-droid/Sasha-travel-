'use client'

/**
 * Sasha 121 · the FORM rung in the chat: a venue whose own booking form Sasha may send (a mapped, approved form — or our
 * test venue). The details come from the saved contact and the request; the read-back lists every field; one yes sends.
 */
import { useEffect, useState } from 'react'
import { contactReq } from '@/lib/booking-client'
import { FormSend } from '../booking-helper/FormSend'

export function ChatBookingForm({ readId, venue, at, party }: { readId: string; venue: string; at: string | null; party: number | null }) {
  const [who, setWho] = useState<{ name: string; phone: string } | null>(null)
  useEffect(() => {
    let off = false
    contactReq('GET').then((r) => {
      if (off) return
      const c = (r.json.contact ?? null) as { name?: string; mobile_e164?: string } | null
      setWho({ name: c?.name ?? '', phone: c?.mobile_e164 ?? '' })
    }).catch(() => { if (!off) setWho({ name: '', phone: '' }) })
    return () => { off = true }
  }, [])
  if (!who) return <div style={{ fontSize: 13, opacity: 0.7 }}>Reading your saved details…</div>
  return <div style={{ background: '#fff', color: '#111', borderRadius: 8, padding: 8 }}>
    <FormSend readId={readId} venueLabel={venue} defaults={{ name: who.name, email: '', phone: who.phone }} at={at} party={party} />
  </div>
}
