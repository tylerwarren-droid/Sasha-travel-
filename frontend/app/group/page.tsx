'use client'
/**
 * Sasha 332 · GROUP MOVEMENT v1 — THE MASTER LIST. One row per worker: transport, hotel, price, limit, status. Read live from each
 * worker's ONE trip (GET /api/booking/group/list — computed on the server, never stored), every 6 s. The organiser's list goes in
 * here too: a .csv / .xlsx file, a photo of the list, or pasted text (POST /api/booking/group/upload); unclear rows come back as ONE
 * question.
 *
 * Sasha 346 · EVERY button answers (docs/sasha/S-346-every-button-answers.md): no button is ever greyed out (a grey button says nothing —
 * Tyler's Swap and Book all, 5 Nov) and none opens a pop-up after a wait (blocked: nothing). A press goes to the server, whose ONE outcome
 * (booking_signer/group_outcome.py) says what was done or exactly what's missing; heard() shows every answer — a lost request too.
 */
import { useEffect, useState } from 'react'
import { bookingReq } from '@/lib/booking-client'
import { T, TONE, page, card as cardS, field, btn, btn2, small } from '@/lib/group-theme'   // Sasha 336 · readable on the dark theme

type Row = { member_id: string; name: string; grade?: string | null; home_city?: string | null; out?: string | null; back?: string | null
  transport?: string | null; hotel?: string | null; price_eur?: number | null; flight_eur?: number | null; hotel_eur_per_night?: number | null
  limit: { flight_return_eur?: number; hotel_night_eur?: number }; status: string; vault?: { passport: boolean; loyalty: string[] } }
type View = { movement?: { company?: string; destination?: string; starts_on?: string; ends_on?: string; hotel_area?: string }
  rows: Row[]; counts?: Record<string, number>; why?: string }

const eur = (n?: number | null) => (typeof n === 'number' ? `€${Math.round(n)}` : '—')

export default function GroupPage() {
  const [v, setV] = useState<View | null>(null)
  const [text, setText] = useState('')
  const [said, setSaid] = useState<string | null>(null)
  const [busy, setBusyName] = useState<string | null>(null)   // Sasha 346 · WHAT is running — a press meanwhile is told so, never ignored
  const setBusy = (b: boolean | string) => setBusyName(b === true ? 'That' : b || null)
  const [missing, setMissing] = useState<string[]>([])   // Sasha 346 · the fields the server named as missing (their inputs are marked)
  const [invoiceLink, setInvoiceLink] = useState<string | null>(null)
  const [links, setLinks] = useState<{ name: string; link: string }[]>([])
  // Sasha 334 · a master-list action's card: AgAPI's read-backs + the Yes / No the server gives (sasha.yes_buttons — 330's one place)
  const [card, setCard] = useState<{ read_back_id: string; read_back: string[]; ask: string; choices: { title: string; route: string }[] } | null>(null)
  const [swapIn, setSwapIn] = useState('')
  const [queue, setQueue] = useState<NonNullable<typeof card>[]>([])   // Sasha 340 · moved fares: one card each, shown in turn
  const [swapOut, setSwapOut] = useState('')
  const [swapCity, setSwapCity] = useState('')   // Sasha 336 · a newcomer: the swap adds them and invites them to their vault
  const [swapGrade, setSwapGrade] = useState('')
  // Sasha 336 · "Book all" with nothing bookable: a short list with taps (book anyway / invite)
  const [taps, setTaps] = useState<{ label?: string; say?: string; act?: { action: 'book' | 'swap'; who: string[]; to?: string; over_ok: boolean }; invite?: string[] }[]>([])

  useEffect(() => {
    let off = false
    const pull = async () => {
      const r = await bookingReq('/api/booking/group/list').catch(() => null)
      if (!off && r?.ok) setV(r.json as unknown as View)
    }
    pull()
    bookingReq('/api/booking/group/waiting').then(r => {   // Sasha 340 · a moved fare's card survives a reload
      const re = ((r?.json || {}) as { reasked?: NonNullable<typeof card>[] }).reasked || []
      if (!off && re.length) { setCard(re[0]); setQueue(re.slice(1)) }
    }).catch(() => {})
    const t = setInterval(pull, 6000)
    return () => { off = true; clearInterval(t) }
  }, [])

  // Sasha 346 · THE ONE READER of every answer: the server's words (say / why / message), else what happened to the request — never empty
  const heard = (name: string, r: { ok: boolean; status: number; json: Record<string, unknown> } | null): Record<string, unknown> => {
    const j = (r?.json || {}) as Record<string, unknown>
    const words = String(j.say || j.why || j.message || '').trim()
    setMissing(Array.isArray(j.missing) ? (j.missing as string[]) : [])
    setSaid(words || (!r ? `${name}: Sasha’s server didn’t answer — nothing was changed. Try again.`
      : `${name}: the server answered ${r.status} without words — nothing was changed. Try again.`))
    return j
  }
  // a press while another action runs is TOLD so — the button is never greyed out
  const press = (name: string, fn: () => Promise<unknown>) => () => {
    if (busy) { setSaid(`${busy} is still running — its answer comes here first. Then ${name}.`); return }
    setInvoiceLink(null)
    fn().catch(e => { setBusy(false); setSaid(`${name}: ${(e as Error).message || 'it didn’t go through'} — nothing was changed. Try again.`) })
  }
  const send = async (body: Record<string, unknown>) => {
    setBusy('Add these'); setSaid('Adding…')
    const r = await bookingReq('/api/booking/group/upload', body, 60000).catch(() => null)
    setBusy(false)
    heard('Add these', r)
  }
  const invite = async (who: string[] | null) => {   // Sasha 333 · each member's own secure page — never collected in chat
    setBusy('Invite'); setSaid('Inviting…')
    const r = await bookingReq('/api/booking/group/invite', { who }, 60000).catch(() => null)
    setBusy(false)
    const j = heard('Invite', r) as { forward?: { name: string; link: string }[] }
    setLinks(j.forward || [])
  }
  // Sasha 339 · what an act answered: ONE card (its Yes / No), or what held each worker (taps), said as it is
  const show = (j: Record<string, unknown>) => {
    if (j.status === 'awaiting_yes' && Array.isArray(j.choices)) setCard(j as unknown as NonNullable<typeof card>)
    const re = (Array.isArray(j.reasked) ? j.reasked : []) as NonNullable<typeof card>[]
    if (re.length) { setCard(re[0]); setQueue(re.slice(1)) }   // Sasha 340 · a moved fare: THAT worker's card, its own Yes
    if (j.status === 'awaiting_yes') setSaid(Array.isArray(j.taps) && j.taps.length ? 'Some are held — see below the card.' : 'Read the card, then Yes or No.')
    else heard('That', { ok: true, status: 200, json: j })   // Sasha 346 · the ONE reader
    if (Array.isArray(j.taps)) setTaps(j.taps as typeof taps)
    if (Array.isArray(j.links)) setLinks(j.links as { name: string; link: string }[])
  }
  // Sasha 339 · BOOK is ONE background job on the server: follow it ("Preparing 18… 12 ready"), then its ONE card. A lost request is
  // said as one — never "Nothing to do."
  const follow = async () => {
    for (let i = 0; i < 300; i++) {
      const r = await bookingReq('/api/booking/group/job').catch(() => null)
      const j = (r?.json || {}) as { state?: string; say?: string; result?: Record<string, unknown> }
      if (r?.ok && j.state === 'ready' && j.result) { setBusy(false); show(j.result); return }
      if (r?.ok && j.state === 'failed') { setBusy(false); setSaid(j.say || 'The read-backs couldn’t be prepared — nothing was booked. Try again.'); return }
      if (r?.ok && j.say) setSaid(j.say)
      await new Promise(res => setTimeout(res, 2000))
    }
    setBusy(false); setSaid('Still preparing — this page stopped waiting. Nothing is booked; reload to see the card.')
  }
  const act = async (action: 'book' | 'swap' | 'cancel', who: string[] | null, to?: string, more: Record<string, unknown> = {}) => {
    const name = { book: 'Book', swap: 'Swap', cancel: 'Cancel' }[action]
    setBusy(name); setCard(null); setTaps([]); setSaid(action === 'swap' ? 'Swapping…' : action === 'book' ? 'Checking who can be booked…' : 'Checking…')
    const r = await bookingReq('/api/booking/group/act', { action, who, to, ...more }, 120000).catch(() => null)
    const j = (r?.json || {}) as Record<string, unknown>
    if (!r?.ok) { setBusy(false); heard(name, r); return }
    if (j.status === 'preparing') { if (j.say) setSaid(String(j.say)); if (Array.isArray(j.taps)) setTaps(j.taps as typeof taps); return follow() }
    setBusy(false); show(j)
  }
  // Sasha 346 · every field goes to the server as typed — IT names what's missing (who leaves · who comes · their home city)
  const swap = () => act('swap', [swapOut.trim()], swapIn.trim(), { to_city: swapCity.trim(), to_grade: swapGrade.trim() })
  const answer = async (choice: string) => {   // once per card: the server holds the claim; a second tap finds nothing
    if (!card) { setSaid('That card was already answered — the master list shows what was done.'); return }
    const id = card.read_back_id
    setCard(null); setBusy('Your answer on the card'); setSaid(choice === 'group_yes' ? 'Booking…' : 'Saying no…')
    const r = await bookingReq('/api/booking/group/confirm', { card: id, choice }, 120000).catch(() => null)
    const j = (r?.json || {}) as Record<string, unknown>
    if (!r?.ok) { setBusy(false); heard('Your answer', r); return }
    if (j.status === 'booking') { if (j.say) setSaid(String(j.say)); return follow() }   // Sasha 339 · several acts: ONE job, followed
    setBusy(false)
    if (Array.isArray(j.reasked) && j.reasked.length) return show(j)
    heard('Your answer', r)
    if (queue.length) { setCard(queue[0]); setQueue(queue.slice(1)) }   // the next moved fare's own card
  }
  // Sasha 346 · the invoice's answer is SAID, and its link shown to tap — a pop-up opened after a wait is blocked (it said nothing)
  const invoice = async () => {
    setBusy('The invoice'); setSaid('Reading the invoice…')
    const r = await bookingReq('/api/booking/group/invoice').catch(() => null)
    setBusy(false)
    const link = (heard('The invoice', r) as { link?: string }).link
    setInvoiceLink(link || null)
  }
  const onFile = (f: File | undefined) => {
    if (!f) return
    const rd = new FileReader()
    rd.onload = () => send({ name: f.name, media_type: f.type, content_base64: String(rd.result).split(',')[1] || '' })
    rd.readAsDataURL(f)
  }

  const mark = (f: string) => (missing.includes(f) ? { ...field, borderColor: T.vault, boxShadow: `0 0 0 1px ${T.vault}` } : field)   // named as missing
  const mv = v?.movement
  return (
    <main style={{ ...page, maxWidth: 1100, margin: '0 auto', padding: '24px 16px' }}>
      <h1 style={{ fontSize: 22, margin: '0 0 4px' }}>{mv?.company ? `${mv.company} → ${mv.destination}` : 'Group movement'}</h1>
      {mv && <p style={{ margin: '0 0 16px', color: T.muted }}>{[mv.starts_on, mv.ends_on].filter(Boolean).join(' – ')}{mv.hotel_area ? ` · hotel ${mv.hotel_area}` : ''}</p>}
      {v?.counts && <p data-counts style={{ margin: '0 0 16px' }}>{Object.entries(v.counts).map(([s, n]) => `${n} ${s}`).join(' · ')}</p>}
      <section style={{ ...cardS, marginBottom: 16 }}>
        <label style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Add the list — a spreadsheet, a photo of it, or paste it</label>
        <input type="file" accept=".csv,.xlsx,image/*" onChange={e => press('Add these', async () => onFile(e.target.files?.[0]))()} style={{ color: T.text }} />
        <textarea value={text} onChange={e => setText(e.target.value)} placeholder="Name, home city, out, back, grade — one person per line"
          rows={3} style={{ ...field, display: 'block', width: '100%', marginTop: 8 }} />
        <button type="button" onClick={press('Add these', () => send({ text }))} style={{ ...btn2, marginTop: 8 }}>Add these</button>
        {said && <p data-upload-said data-said role="status" aria-live="polite" style={{ whiteSpace: 'pre-line', marginTop: 8 }}>{said}</p>}
        {invoiceLink && <p data-invoice-link><a href={invoiceLink} target="_blank" rel="noopener" style={{ color: T.link, textDecoration: 'underline' }}>Open the invoice</a></p>}
        {taps.length > 0 && <div data-taps style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          {taps.map((t, i) => <span key={i} style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            {t.say && <span style={{ color: T.muted }}>{t.say}</span>}
            {t.act ? <button type="button" style={btn} onClick={press(t.label || 'Book anyway', () => act(t.act!.action, t.act!.who, t.act!.to, { over_ok: true }))}>{t.label}</button>
              : t.invite ? <button type="button" style={btn2} onClick={press('Invite', () => invite(t.invite!))}>{t.label}</button> : null}</span>)}
        </div>}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
          <button type="button" onClick={press('Invite everyone', () => invite(null))} style={btn2}>Invite everyone to the vault</button>
          <button type="button" onClick={press('Book all', () => act('book', null))} style={btn}>Book all planned</button>
          <button type="button" onClick={press('The invoice', invoice)} style={btn2}>The invoice</button>
        </div>
        <div data-swap style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10, alignItems: 'center' }}>
          <input value={swapOut} onChange={e => setSwapOut(e.target.value)} placeholder="Swap… (who leaves)" aria-label="who leaves" style={mark('who leaves')} />
          <input value={swapIn} onChange={e => setSwapIn(e.target.value)} placeholder="for… (who comes)" aria-label="who comes" style={mark('who comes')} />
          <input value={swapCity} onChange={e => setSwapCity(e.target.value)} placeholder="their home city (if new)" aria-label="their home city" style={mark('their home city')} />
          <input value={swapGrade} onChange={e => setSwapGrade(e.target.value)} placeholder="grade (if new)" aria-label="grade" style={{ ...field, width: 130 }} />
          <button type="button" onClick={press('Swap', swap)} style={btn2}>Swap</button>
        </div>
        {card && <div data-group-card style={{ ...cardS, background: T.bg, marginTop: 10 }}>
          {card.read_back.map((l, i) => <div key={i} style={{ fontSize: 14 }}>{l || '\u00a0'}</div>)}
          <p style={{ fontWeight: 600 }}>{card.ask}</p>
          {card.choices.map((c, i) => <button key={c.route} type="button" onClick={press(c.title, () => answer(c.route))} style={{ ...(i === 0 ? btn : btn2), marginRight: 8 }}>{c.title}</button>)}
        </div>}
        {links.length > 0 && <ul data-forward>{links.map(l => <li key={l.link}>{l.name}: <a href={l.link} style={{ color: T.link, textDecoration: 'underline' }}>their secure link</a></li>)}</ul>}
      </section>
      {!v ? <p>Loading…</p> : v.why ? <p>{v.why}</p> : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead><tr>{['Name', 'Grade', 'From', 'Transport', 'Hotel', 'Price', 'Limit', 'Vault', 'Status'].map(h =>
              <th key={h} style={{ textAlign: 'left', borderBottom: `1px solid ${T.border}`, padding: '6px 8px', color: T.muted }}>{h}</th>)}</tr></thead>
            <tbody>{v.rows.map(r => (
              <tr key={r.member_id} data-status={r.status} style={{ borderBottom: `1px solid ${T.second}` }}>
                <td style={{ padding: '6px 8px' }}>{r.name}</td>
                <td style={{ padding: '6px 8px' }}>{r.grade || '—'}</td>
                <td style={{ padding: '6px 8px' }}>{r.home_city || '—'}</td>
                <td style={{ padding: '6px 8px' }}>{r.transport || '—'}</td>
                <td style={{ padding: '6px 8px' }}>{r.hotel ? `${r.hotel}${r.hotel_eur_per_night ? ` (${eur(r.hotel_eur_per_night)}/night, est.)` : ''}` : '—'}</td>
                <td style={{ padding: '6px 8px' }}>{eur(r.price_eur)}</td>
                <td style={{ padding: '6px 8px' }}>{[r.limit.flight_return_eur && `flight ≤ ${eur(r.limit.flight_return_eur)}`,
                  r.limit.hotel_night_eur && `hotel ≤ ${eur(r.limit.hotel_night_eur)}/night`].filter(Boolean).join(' · ') || '—'}</td>
                <td style={{ padding: '6px 8px' }} data-vault>{r.vault?.passport ? 'Passport ✓' : 'Passport missing'}{r.vault?.loyalty?.length ? ` · ${r.vault.loyalty.map(x => `${x} ✓`).join(' · ')}` : ''}
                  {!r.vault?.passport && <button type="button" onClick={press('Invite', () => invite([r.member_id]))} style={{ ...small, marginLeft: 6 }}>Invite</button>}
                  {r.vault?.passport && r.status !== 'booked' && r.status !== 'cancelled' && <button type="button" onClick={press('Book', () => act('book', [r.name]))} style={{ ...small, marginLeft: 6 }}>Book</button>}
                  {r.status === 'booked' && <button type="button" onClick={press('Cancel', () => act('cancel', [r.name]))} style={{ ...small, marginLeft: 6 }}>Cancel</button>}</td>
                <td style={{ padding: '6px 8px', color: TONE[r.status] || T.text, fontWeight: 600 }}>{r.status}</td>
              </tr>))}</tbody>
          </table>
        </div>)}
    </main>)
}
