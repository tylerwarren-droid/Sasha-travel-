'use client'

/**
 * S-75 step 5 · USE SASHA ON WHATSAPP — link this account to the guest's WhatsApp number.
 *
 * The guest ticks the consent sentence (v2; its version and hash prove these exact words were shown), gets a six-digit
 * code (ten minutes, one use) and a wa.me link that opens their WhatsApp with "LINK 123456" ready to send. Sending it
 * proves the number is theirs; nothing is texted to them first. In the SANDBOX phase the number is Twilio's sandbox and
 * the guest must first join it ("join …"), which the server names when it knows the words.
 */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'
import { bookingHeaders, bookingUrl } from '@/lib/booking-api'
import { GatedButton } from './GatedButton'

type View = { linked: boolean; opted_out: boolean; number: string | null; join: string | null
  consent: { version: string; text: string; sha256: string } }
type Code = { code: string; expires_at: string; number: string; wa_link: string; join: string | null }

export function WhatsAppLink() {
  const [view, setView] = useState<View | null>(null)
  const [words, setWords] = useState<string | null>(null)
  const [ticked, setTicked] = useState(false)
  const [code, setCode] = useState<Code | null>(null)
  const [busy, setBusy] = useState(false)

  async function load() {
    const r = await bookingReq('/api/booking/whatsapp')
    if (!r.ok) { setWords(refusal(r.json, r.status)); return }
    setView(r.json as unknown as View)
  }
  useEffect(() => {
    let off = false
    bookingReq('/api/booking/whatsapp').then((r) => {
      if (off) return
      if (r.ok) setView(r.json as unknown as View)
      else setWords(refusal(r.json, r.status))
    }).catch((e) => { if (!off) setWords((e as Error).message) })
    return () => { off = true }
  }, [])

  async function getCode() {
    if (!view) return
    setBusy(true)
    try {
      const r = await bookingReq('/api/booking/whatsapp/link', { consent_version: view.consent.version, consent_sha256: view.consent.sha256 })
      if (!r.ok) { setWords(`No code — ${refusal(r.json, r.status)}.`); return }
      setCode(r.json as unknown as Code)
    } finally { setBusy(false) }
  }

  async function unlink() {
    setBusy(true)
    try {
      const r = await fetch(bookingUrl('/api/booking/whatsapp'), { method: 'DELETE', headers: bookingHeaders() })
      let j: Record<string, unknown> = {}
      try { j = await r.json() } catch { /* reported by its status */ }
      setWords(r.ok ? 'Unlinked. Sasha won’t message you on WhatsApp.' : `Not unlinked — ${refusal(j, r.status)}.`)
      setCode(null)
      await load()
    } finally { setBusy(false) }
  }

  return (
    <section id="whatsapp" className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">Use Sasha on WhatsApp</h2>
      {words && <p>{words}</p>}
      {view && !view.number && <p className="opacity-75">Sasha isn&rsquo;t on WhatsApp for guests on this server yet.</p>}
      {view && view.number && view.linked && (
        <div className="space-y-1">
          <p>Linked{view.opted_out ? ' — but you sent STOP, so Sasha sends nothing there. Send START to resume.' : '. Message Sasha on WhatsApp to book.'}</p>
          <GatedButton label="Unlink" onClick={() => { unlink().catch((e) => setWords((e as Error).message)) }} needs={[busy && 'the last step to finish']} />
        </div>
      )}
      {view && view.number && !view.linked && !code && (
        <div className="space-y-2">
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={ticked} onChange={(e) => setTicked(e.target.checked)} />
            <span>{view.consent.text}</span>
          </label>
          <GatedButton label="Get my link code" onClick={() => { getCode().catch((e) => setWords((e as Error).message)) }}
            needs={[!ticked && 'the box above ticked', busy && 'the last step to finish']} />
        </div>
      )}
      {code && (
        <div className="space-y-1">
          {code.join && <p>1. This is Twilio&rsquo;s test number: first send <strong>{code.join}</strong> to {code.number} on WhatsApp.</p>}
          <p>{code.join ? '2. ' : ''}Then send <strong>LINK {code.code}</strong> to {code.number} — this button opens WhatsApp with it ready:</p>
          <a className="inline-block rounded border px-3 py-1" href={code.wa_link} target="_blank" rel="noopener noreferrer">Open WhatsApp ↗</a>
          <p className="text-xs opacity-70">The code works once, for ten minutes.</p>
        </div>
      )}
    </section>
  )
}
