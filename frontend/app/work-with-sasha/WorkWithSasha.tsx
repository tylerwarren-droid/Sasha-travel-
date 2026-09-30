'use client'

/**
 * S-55 · "Work with Sasha" — a venue opts in (S-49 §2 method 3, S-50 §3).
 *
 * Every state says what is true:
 *   · the server says the page is closed      → the pitch, and "Sign-up isn't open yet." — no form that cannot send
 *   · the server can't be reached             → said; no form
 *   · open                                    → three UNTICKED boxes, each showing the exact v2 wording it would record
 *                                               (fetched from the server), the authority tick, and the send button
 *   · sent                                    → "we've emailed a link"; nothing is consent until it is confirmed
 *   · refused                                 → the server's own words
 * The hash of each wording AS DISPLAYED goes with the submission; the server refuses if it is not what it would store.
 */
import { useEffect, useState } from 'react'
import { CHANNELS, COPY, call, sha256hex, type Channel, type Lang } from './copy'

type Status = { phase: 'loading' } | { phase: 'closed' } | { phase: 'unreachable' } | { phase: 'open'; wordings: Record<Channel, string> }
type Send = { phase: 'idle' } | { phase: 'sending' } | { phase: 'sent'; email: string } | { phase: 'refused'; message: string }

const E164 = /^\+[1-9]\d{7,14}$/
const HTTPS = /^https?:\/\/[^\s/.]+\.[^\s]+$/
const EMAIL = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/

export default function WorkWithSasha({ lang }: { lang: Lang }) {
  const t = COPY[lang]
  const [status, setStatus] = useState<Status>({ phase: 'loading' })
  const [send, setSend] = useState<Send>({ phase: 'idle' })
  const [ticked, setTicked] = useState<Record<Channel, boolean>>({ whatsapp: false, web_submit: false, email_confirm: false })
  const [f, setF] = useState({ number: '', url: '', venue: '', website: '', country: 'ES', name: '', role: '', email: '', authorised: false })

  useEffect(() => {
    let off = false
    ;(async () => {
      try {
        const s = await call('status')
        if (off) return
        if (!s.ok) { setStatus({ phase: 'unreachable' }); return }
        if (!s.json.open) { setStatus({ phase: 'closed' }); return }
        const w = await call('wordings', undefined, lang)
        if (off) return
        const wordings = (w.json.wordings ?? null) as Record<Channel, string> | null
        setStatus(w.ok && wordings ? { phase: 'open', wordings } : { phase: 'unreachable' })
      } catch {
        if (!off) setStatus({ phase: 'unreachable' })
      }
    })()
    return () => { off = true }
  }, [lang])

  const number = f.number.replace(/[\s().-]/g, '')
  const url = f.url.trim()
  const shown = (ch: Channel, wordings: Record<Channel, string>) =>
    ch === 'web_submit' ? wordings.web_submit.split('{url}').join(url || t.urlPlaceholder) : wordings[ch]

  const needs = [
    !CHANNELS.some((c) => ticked[c]) && t.need.channel,
    ticked.whatsapp && !E164.test(number) && t.need.number,
    ticked.web_submit && !HTTPS.test(url) && t.need.url,
    f.venue.trim().length < 2 && t.need.venue,
    f.name.trim().length < 2 && t.need.name,
    f.role.trim().length < 2 && t.need.role,
    !EMAIL.test(f.email.trim()) && t.need.email,
    !f.authorised && t.need.authorised,
  ].filter(Boolean) as string[]

  async function submit(wordings: Record<Channel, string>) {
    setSend({ phase: 'sending' })
    const channels: Record<string, unknown> = {}
    const hashes: Record<string, string> = {}
    for (const ch of CHANNELS) {
      if (!ticked[ch]) continue
      channels[ch] = ch === 'whatsapp' ? { number } : ch === 'web_submit' ? { url } : {}
      hashes[ch] = await sha256hex(shown(ch, wordings))
    }
    try {
      const r = await call('request', {
        lang, venue_name: f.venue, country: f.country, website: f.website.trim() || null, contact_name: f.name,
        contact_role: f.role, email: f.email.trim(), authorised: f.authorised, channels, shown: hashes,
      })
      if (r.ok && r.json.status === 'sent') setSend({ phase: 'sent', email: String(r.json.email) })
      else setSend({ phase: 'refused', message: String(r.json.message ?? r.json.rule ?? `HTTP ${r.status}`) })
    } catch (e) {
      setSend({ phase: 'refused', message: (e as Error).message })
    }
  }

  const input = 'w-full rounded border px-2 py-1'
  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-10 text-[15px] leading-relaxed">
      <p className="mb-6 text-sm"><a className="underline" href={`?lang=${lang === 'en' ? 'es' : 'en'}`}>{lang === 'en' ? 'Español' : 'English'}</a></p>
      <h1 className="text-2xl font-semibold">{t.title}</h1>
      <p className="mt-4 font-semibold">{t.lead}</p>
      <p className="mt-3">{t.pitch}</p>
      <p className="mt-3 text-sm opacity-80">{t.notYet}</p>

      {status.phase === 'loading' && <p className="mt-8 text-sm">{t.loading}</p>}
      {status.phase === 'closed' && <p className="mt-8 font-medium">{t.closed}</p>}
      {status.phase === 'unreachable' && <p className="mt-8 font-medium">{t.unreachable}</p>}

      {status.phase === 'open' && send.phase !== 'sent' && (
        <form className="mt-8 space-y-6" onSubmit={(e) => { e.preventDefault(); if (!needs.length) void submit(status.wordings) }}>
          <div>
            <p className="font-semibold">{t.choose}</p>
            <p className="text-sm opacity-80">{t.noneTicked}</p>
          </div>
          {CHANNELS.map((ch) => (
            <fieldset key={ch} className="rounded border p-3">
              <label className="flex items-start gap-2 font-medium">
                <input type="checkbox" className="mt-1" checked={ticked[ch]} onChange={(e) => setTicked({ ...ticked, [ch]: e.target.checked })} />
                <span>{t.channel[ch]}</span>
              </label>
              <blockquote className="mt-2 border-l-2 pl-3 text-sm italic">{shown(ch, status.wordings)}</blockquote>
              {ch === 'whatsapp' && ticked.whatsapp && (
                <label className="mt-2 block text-sm">{t.number}<input className={input} inputMode="tel" value={f.number} onChange={(e) => setF({ ...f, number: e.target.value })} /></label>
              )}
              {ch === 'web_submit' && ticked.web_submit && (
                <label className="mt-2 block text-sm">{t.formUrl}<input className={input} inputMode="url" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} /></label>
              )}
              {ch === 'email_confirm' && ticked.email_confirm && <p className="mt-2 text-sm">{t.emailScope}</p>}
            </fieldset>
          ))}

          <div className="grid gap-3 text-sm sm:grid-cols-2">
            <label className="sm:col-span-2">{t.venue}<input className={input} value={f.venue} onChange={(e) => setF({ ...f, venue: e.target.value })} /></label>
            <label>{t.website}<input className={input} inputMode="url" placeholder="https://" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} /></label>
            <label>{t.country}<input className={input} maxLength={2} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value.toUpperCase() })} /></label>
            <label>{t.name}<input className={input} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
            <label>{t.role}<input className={input} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} /></label>
            <label className="sm:col-span-2">{t.email}<input className={input} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
          </div>

          <label className="flex items-start gap-2 font-medium">
            <input type="checkbox" className="mt-1" checked={f.authorised} onChange={(e) => setF({ ...f, authorised: e.target.checked })} />
            <span>{t.authorised}</span>
          </label>

          <p className="text-sm">{t.confirmNote}</p>
          <p className="text-sm"><a className="underline" href={`/sasha-privacy?lang=${lang}`}>{t.privacy}</a> <span className="opacity-70">{t.draft}</span></p>

          <div>
            <button type="submit" disabled={needs.length > 0 || send.phase === 'sending'} className="rounded bg-black px-4 py-2 text-white disabled:opacity-40">
              {send.phase === 'sending' ? t.sending : t.submit}
            </button>
            {needs.length > 0 && <p className="mt-2 text-xs opacity-70">{t.needs}: {needs.join(', ')}</p>}
            {send.phase === 'refused' && <p className="mt-2 text-sm text-red-800">{t.refused} {send.message}</p>}
          </div>
        </form>
      )}

      {send.phase === 'sent' && <p className="mt-8 rounded bg-black/5 p-3 font-medium">{t.sent(send.email)}</p>}

      <p className="mt-12 text-xs opacity-70">{t.operated}</p>
    </main>
  )
}
