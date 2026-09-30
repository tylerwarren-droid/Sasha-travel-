'use client'

/**
 * S-36 · The ladder — Magellan reads what a venue publishes, Sasha says what she can do, the guest picks.
 *
 *   read → "They have no booking form. I'll call them — or I can email and we wait. Which?"
 *   Phone → PhoneCall on the number READ (never typed here)
 *   Email → the exact email read back → yes → sent only when the mail service accepted it → their reply, word for word
 *   WhatsApp → the message written for the guest to send from their own phone
 *
 * Every fact is shown with where it was read. Every step ends in something visible
 * (scripts/check-outcome-surfaces.mjs holds this file to it).
 */
import { useEffect, useRef, useState } from 'react'
import { bookingUrl as apiUrl, bookingHeaders as apiHeaders } from '@/lib/booking-api'
import { GatedButton } from './GatedButton'
import { PhoneCall } from './PhoneCall'

type Fact = { kind: string; value: string; source_label: string; source_url: string }
type Rung = { rung: string; available: boolean; value: string | null; source: string | null; why_not: string | null }
type Read = { read_id: string; venue: string; country: string | null; facts: Fact[]; rungs: Rung[]; say: string; sources: Array<{ url: string; result: string }> }
type Reply = { from: string | null; text: string | null; note: string | null; received_at: string }

const TIMEOUT_MS = 30000

async function req(path: string, body?: unknown): Promise<{ ok: boolean; status: number; json: Record<string, unknown> }> {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS)
  let r: Response
  try {
    r = await fetch(apiUrl(path), body === undefined ? { headers: apiHeaders(), signal: ctl.signal } : { method: 'POST', headers: apiHeaders(), body: JSON.stringify(body), signal: ctl.signal })
  } catch (e) {
    throw new Error((e as Error).name === 'AbortError' ? `Sasha's server did not answer within ${TIMEOUT_MS / 1000}s` : `could not reach Sasha's server (${(e as Error).message})`)
  } finally { clearTimeout(timer) }
  let json: Record<string, unknown> = {}
  try { json = await r.json() } catch { /* reported by status below */ }
  return { ok: r.ok, status: r.status, json }
}

const refusal = (j: Record<string, unknown>, status: number) =>
  `${typeof j.rule === 'string' ? j.rule : `HTTP ${status}`}${typeof j.message === 'string' ? ` — ${j.message}` : ''}`

export function Ladder({ defaults }: { defaults: { name: string; email: string; phone: string } }) {
  const [q, setQ] = useState({ name: '', city: '', country: '', website: '' })
  const [reading, setReading] = useState<'idle' | 'reading' | 'done' | 'stopped'>('idle')
  const [read, setRead] = useState<Read | null>(null)
  const [pick, setPick] = useState<string | null>(null)
  // S-41 G2 · which read phone number to call — the guest chooses, each shown with where it was read
  const [phoneFact, setPhoneFact] = useState<number | null>(null)
  // the booking link · a link can carry the whole booking (…/booking-helper?book=phone&lookup=…&number=…): the page reads the venue
  // itself, and the link's number only PICKS among the numbers read there — it is never dialled from the URL
  const [linked, setLinked] = useState<{ number: string; source: string; date: string; time: string; party: number; name: string } | null>(null)
  const autoRead = useRef(false)
  const [note, setNote] = useState<string | null>(null)

  // email rung
  const [b, setB] = useState({ date: '', time: '20:00', party: 2, name: defaults.name, email: defaults.email })
  const [emailPhase, setEmailPhase] = useState<'idle' | 'preparing' | 'read_back' | 'sending' | 'sent' | 'stopped'>('idle')
  const [emailLines, setEmailLines] = useState<string[]>([])
  const [emailPrep, setEmailPrep] = useState<{ email_id: string; sha256: string } | null>(null)
  const [emailNote, setEmailNote] = useState<string | null>(null)
  const [replies, setReplies] = useState<Reply[]>([])

  // S-37 link rung
  const [link, setLink] = useState<{ link_id: string; url: string; sha256: string; platform: string; lines: string[] } | null>(null)
  const [linkStatus, setLinkStatus] = useState<string | null>(null)
  const [linkNote, setLinkNote] = useState<string | null>(null)
  const [linkConfs, setLinkConfs] = useState<Array<{ text: string | null; counted: boolean; note: string | null }>>([])

  type Linked = { number: string; source: string; date: string; time: string; party: number; name: string }

  async function doRead(query = q, link: Linked | null = linked) {
    setReading('reading'); setRead(null); setPick(null); setNote(null)
    const r = await req('/api/booking/venues/read', { name: query.name, city: query.city, country: query.country || undefined, website: query.website || undefined })
    if (!r.ok) { setReading('stopped'); setNote(`Could not read them: ${refusal(r.json, r.status)}`); return }
    const got = r.json as unknown as Read
    setRead(got); setReading('done')
    if (link) {
      const digits = (s: string) => s.replace(/[^\d+]/g, '')
      const want = digits(link.number)
      const i = got.facts.findIndex((f) => f.kind === 'phone' && digits(f.value) === want
        && (link.source !== 'google' || /google listing/i.test(f.source_label)))
      if (i < 0) { setNote(`The number in the link (${link.number}) is not among the numbers read for ${got.venue} — choose one below, or none.`); setPick('phone'); return }
      setPick('phone'); setPhoneFact(i)
    }
  }

  useEffect(() => {
    if (autoRead.current) return
    const u = new URLSearchParams(window.location.search)
    if (u.get('book') !== 'phone' || !u.get('lookup') || !u.get('city')) return
    autoRead.current = true
    const query = { name: u.get('lookup') ?? '', city: u.get('city') ?? '', country: (u.get('country') ?? '').toUpperCase(), website: '' }
    const party = Number(u.get('party'))
    const link: Linked = { number: u.get('number') ?? '', source: (u.get('number_source') ?? '').toLowerCase(), date: u.get('date') ?? '',
      time: u.get('time') ?? '', party: Number.isInteger(party) && party >= 1 && party <= 20 ? party : 2, name: u.get('name') ?? defaults.name }
    ;(async () => {
      await Promise.resolve()
      setQ(query); setLinked(link)
      await doRead(query, link)
    })().catch((e) => { setReading('stopped'); setNote(`Stopped: ${(e as Error).message}`) })
  // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, from the page's own URL
  }, [])

  async function prepareEmail() {
    if (!read) return
    setEmailPhase('preparing'); setEmailNote(null)
    const r = await req('/api/booking/emails', { read_id: read.read_id, ...b })
    if (!r.ok) { setEmailPhase('stopped'); setEmailNote(`Not written: ${refusal(r.json, r.status)}. Nothing was sent.`); return }
    const rb = r.json.read_back as { lines: string[]; sha256: string }
    setEmailLines(rb.lines); setEmailPrep({ email_id: r.json.email_id as string, sha256: rb.sha256 }); setEmailPhase('read_back')
  }

  async function sendEmail() {
    if (!emailPrep) return
    setEmailPhase('sending'); setEmailNote(null)
    const r = await req(`/api/booking/emails/${emailPrep.email_id}/send`, { read_back_sha256: emailPrep.sha256, approval: { how: 'button', said: null } })
    if (!r.ok) { setEmailPhase('stopped'); setEmailNote(`Not sent: ${refusal(r.json, r.status)}.`); return }
    setEmailNote(String(r.json.say ?? ''))
    setEmailPhase(r.json.status === 'sent' ? 'sent' : 'stopped')
  }

  async function checkReplies() {
    if (!emailPrep) return
    const g = await req(`/api/booking/emails/${emailPrep.email_id}`)
    if (!g.ok) { setEmailNote(`Could not check for a reply: ${refusal(g.json, g.status)}`); return }
    setReplies((g.json.replies as Reply[]) ?? []); setEmailNote(String(g.json.say ?? ''))
  }

  const run = (f: () => Promise<void>, onFail: (m: string) => void) => () => {
    f().catch((e) => onFail(`Stopped: ${(e as Error).message}. Nothing more was done.`))
  }

  async function prepareLink() {
    if (!read) return
    setLinkNote(null)
    const r = await req('/api/booking/links', { read_id: read.read_id, date: b.date, time: b.time, party: b.party, name: b.name })
    if (!r.ok) { setLinkNote(`No link: ${refusal(r.json, r.status)}`); return }
    const rb = r.json.read_back as { lines: string[]; sha256: string }
    setLink({ link_id: r.json.link_id as string, url: r.json.url as string, sha256: rb.sha256, platform: r.json.platform as string, lines: rb.lines })
    setLinkStatus('offered')
  }

  async function linkState(path: string, body?: unknown) {
    if (!link) return
    const g = await req(`/api/booking/links/${link.link_id}${path}`, body)
    if (!g.ok) { setLinkNote(`Could not record it: ${refusal(g.json, g.status)}`); return }
    setLinkStatus(String(g.json.status ?? '')); setLinkNote(typeof g.json.say === 'string' ? g.json.say : null)
    if (Array.isArray(g.json.confirmations)) setLinkConfs(g.json.confirmations as Array<{ text: string | null; counted: boolean; note: string | null }>)
  }

  const rung = (k: string) => read?.rungs.find((r) => r.rung === k)
  const wa = rung('whatsapp')
  const waText = `Hello, I'd like to book a table for ${b.party} on ${b.date || '[date]'} at ${b.time}, under the name ${b.name}. Thank you!`

  return (
    <section className="mt-8 rounded border p-4">
      <h2 className="text-lg font-semibold">Find how to book a venue</h2>
      <p className="text-sm opacity-80">Sasha reads what the venue publishes — its site, or its Google listing — and tells you what she can do.</p>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <label>Venue <input className="w-full rounded border px-2 py-1" value={q.name} onChange={(e) => setQ({ ...q, name: e.target.value })} /></label>
        <label>City <input className="w-full rounded border px-2 py-1" value={q.city} onChange={(e) => setQ({ ...q, city: e.target.value })} /></label>
        <label>Country (ES, PT…) <input className="w-full rounded border px-2 py-1" value={q.country} onChange={(e) => setQ({ ...q, country: e.target.value })} /></label>
        <label>Their website (optional) <input className="w-full rounded border px-2 py-1" placeholder="https://…" value={q.website} onChange={(e) => setQ({ ...q, website: e.target.value })} /></label>
      </div>
      <div className="mt-2">
        <GatedButton label="Look them up" onClick={run(doRead, (m) => { setReading('stopped'); setNote(m) })}
          needs={[q.name.trim().length < 2 && 'a venue name', q.city.trim().length < 2 && 'a city', reading === 'reading' && 'the read to finish']} />
      </div>
      {note && <p className="mt-2 text-sm">{note}</p>}

      {read && (
        <div className="mt-4 text-sm">
          <p className="font-medium">{read.say}</p>
          <ul className="ml-5 mt-1 list-disc">
            {read.facts.map((f, i) => <li key={i}>{f.kind}: {f.value} <span className="opacity-60">— on {f.source_label}</span></li>)}
          </ul>
          {read.facts.length === 0 && <p className="opacity-70">Nothing published was found. What was tried: {read.sources.map((s) => `${s.url} (${s.result})`).join('; ')}</p>}
          <ul className="mt-2">
            {read.rungs.filter((r) => !r.available && r.why_not).map((r, i) => <li key={i} className="text-xs opacity-70">{r.rung}: {r.why_not}</li>)}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            {rung('link')?.available && <GatedButton label={`Their ${rung('link')?.value} page`} onClick={() => setPick('link')} needs={[]} done={pick === 'link' && 'Chosen'} />}
            {rung('phone')?.available && <GatedButton label="Phone them" onClick={() => setPick('phone')} needs={[]} done={pick === 'phone' && 'Chosen'} />}
            {rung('email')?.available && <GatedButton label="Email them" onClick={() => setPick('email')} needs={[]} done={pick === 'email' && 'Chosen'} />}
            {wa?.available && <GatedButton label="WhatsApp (you send it)" onClick={() => setPick('whatsapp')} needs={[]} done={pick === 'whatsapp' && 'Chosen'} />}
          </div>
        </div>
      )}

      {read && pick === 'phone' && (
        <div className="mt-4 rounded border p-3 text-sm">
          <p className="font-medium">Which number should Sasha call?</p>
          {read.facts.map((f, i) => f.kind === 'phone' && (
            <label key={i} className="block">
              <input type="radio" name="phone-fact" checked={phoneFact === i} onChange={() => setPhoneFact(i)} /> {f.value} <span className="opacity-60">— on {f.source_label}</span>
            </label>
          ))}
          {phoneFact === null
            ? <p className="text-xs opacity-70">Waiting for: a number to be chosen.</p>
            : <PhoneCall key={phoneFact} defaults={{ name: linked?.name || defaults.name, phone: '' }} readId={read.read_id} venueLabel={read.venue} factIndex={phoneFact}
                initial={linked ? { date: linked.date, time: linked.time, party: linked.party } : undefined} />}
        </div>
      )}

      {read && pick === 'email' && (
        <div className="mt-4 rounded border p-3 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <label>Date <input className="w-full rounded border px-2 py-1" type="date" value={b.date} onChange={(e) => setB({ ...b, date: e.target.value })} /></label>
            <label>Time <input className="w-full rounded border px-2 py-1" type="time" value={b.time} onChange={(e) => setB({ ...b, time: e.target.value })} /></label>
            <label>Party <input className="w-full rounded border px-2 py-1" type="number" min={1} max={20} value={b.party} onChange={(e) => setB({ ...b, party: Number(e.target.value) })} /></label>
            <label>Name <input className="w-full rounded border px-2 py-1" value={b.name} onChange={(e) => setB({ ...b, name: e.target.value })} /></label>
            <label className="col-span-2">Your email — copied, so you hold the thread <input className="w-full rounded border px-2 py-1" value={b.email} onChange={(e) => setB({ ...b, email: e.target.value })} /></label>
          </div>
          <div className="mt-2">
            <GatedButton label="Write the email" onClick={run(prepareEmail, (m) => { setEmailPhase('stopped'); setEmailNote(m) })}
              needs={[!b.date && 'a date', !b.email.includes('@') && 'your email', emailPhase === 'preparing' && 'the email to be written', (emailPhase === 'sending' || emailPhase === 'sent') && 'nothing — it has been sent']} />
          </div>
          {emailLines.length > 0 && (
            <div className="mt-3 rounded bg-black/5 p-3">
              <p className="font-medium">This exact email — your yes covers every word:</p>
              {emailLines.map((l, i) => <p key={i} className="whitespace-pre-wrap">{l}</p>)}
              <div className="mt-2">
                <GatedButton label="Yes — send it" onClick={run(sendEmail, (m) => { setEmailPhase('stopped'); setEmailNote(m) })}
                  needs={[emailPhase !== 'read_back' && emailPhase !== 'sending' && emailPhase !== 'sent' && 'a fresh read-back']}
                  done={(emailPhase === 'sending' || emailPhase === 'sent') && 'Approved — sent at most once per yes.'} />
              </div>
            </div>
          )}
          {emailNote && <p className="mt-2">{emailNote}</p>}
          {emailPhase === 'sent' && (
            <div className="mt-2">
              <GatedButton label="Check for their reply" onClick={run(checkReplies, setEmailNote)} needs={[]} />
              {replies.map((r, i) => (
                <div key={i} className="mt-2 rounded border p-2">
                  <p className="text-xs opacity-70">From {r.from ?? 'unknown'} at {r.received_at}</p>
                  {r.text ? <p className="whitespace-pre-wrap">“{r.text}”</p> : <p className="opacity-70">{r.note}</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {read && pick === 'link' && (
        <div className="mt-4 rounded border p-3 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <label>Date <input className="w-full rounded border px-2 py-1" type="date" value={b.date} onChange={(e) => setB({ ...b, date: e.target.value })} /></label>
            <label>Time <input className="w-full rounded border px-2 py-1" type="time" value={b.time} onChange={(e) => setB({ ...b, time: e.target.value })} /></label>
            <label>Party <input className="w-full rounded border px-2 py-1" type="number" min={1} max={20} value={b.party} onChange={(e) => setB({ ...b, party: Number(e.target.value) })} /></label>
            <label>Name <input className="w-full rounded border px-2 py-1" value={b.name} onChange={(e) => setB({ ...b, name: e.target.value })} /></label>
          </div>
          <div className="mt-2">
            <GatedButton label="Prepare the link" onClick={run(prepareLink, setLinkNote)} needs={[!b.date && 'a date', link !== null && 'nothing — the link is ready below']} />
          </div>
          {link && (
            <div className="mt-3 rounded bg-black/5 p-3">
              {link.lines.map((l, i) => <p key={i}>{l}</p>)}
              <a className="mt-2 inline-block rounded border px-3 py-1" href={link.url} target="_blank" rel="noreferrer"
                onClick={() => { linkState('/opened', { read_back_sha256: link.sha256 }).catch((e) => setLinkNote(`Opened, but not recorded: ${(e as Error).message}`)) }}>
                Open their {link.platform} page
              </a>
              <div className="mt-2 flex gap-2">
                <GatedButton label="I booked it" onClick={run(() => linkState('/booked', { how: 'button' }), setLinkNote)}
                  needs={[linkStatus === 'offered' && 'their page to be opened first']} done={(linkStatus === 'guest_booked' || linkStatus === 'confirmed') && 'Noted'} />
                <GatedButton label="Check for the confirmation" onClick={run(() => linkState(''), setLinkNote)} needs={[]} />
              </div>
            </div>
          )}
          {linkNote && <p className="mt-2">{linkNote}</p>}
          {linkConfs.map((c, i) => (
            <div key={i} className="mt-2 rounded border p-2">
              {c.text ? <p className="whitespace-pre-wrap">“{c.text}”</p> : null}
              {!c.counted && <p className="text-xs opacity-70">Not counted as the confirmation: {c.note}</p>}
            </div>
          ))}
        </div>
      )}

      {read && pick === 'whatsapp' && wa?.value && (
        <div className="mt-4 rounded border p-3 text-sm">
          <p>This opens WhatsApp on your phone with the message written. <strong>You</strong> press send, and their reply comes to you.</p>
          <p className="mt-1 whitespace-pre-wrap">“{waText}”</p>
          <a className="mt-2 inline-block rounded border px-3 py-1" href={`https://wa.me/${wa.value.replace('+', '')}?text=${encodeURIComponent(waText)}`} target="_blank" rel="noreferrer">Open WhatsApp</a>
        </div>
      )}
    </section>
  )
}
