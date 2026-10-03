'use client'

/** Sasha 121 · OPS: invite a guest — sign-up is invite-only until counsel approves the privacy notice and the terms. */
import { useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'
import { GatedButton } from './GatedButton'

export function InviteGuest() {
  const [email, setEmail] = useState('')
  const [words, setWords] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const ok = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(email.trim())
  async function send() {
    setBusy(true)
    try {
      const r = await bookingReq('/api/booking/ops/invite', { email: email.trim() })
      setWords(r.ok ? String(r.json.say) : `Not sent — ${refusal(r.json, r.status)}.`)
      if (r.ok) setEmail('')
    } catch (e) { setWords((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <section className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">Invite a guest</h2>
      <p className="opacity-75">Sign-up is invite-only. Sasha emails them a link from her own address; it works once, for 24 hours.</p>
      <input className="w-full rounded border px-2 py-1" placeholder="their email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <GatedButton label="Send the invitation" onClick={() => { send() }} needs={[!ok && 'an email address', busy && 'the last step to finish']} />
      {words && <p>{words}</p>}
    </section>
  )
}
