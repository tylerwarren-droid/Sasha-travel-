'use client'
/**
 * Sasha 332 · GROUP MOVEMENT v1 — THE MASTER LIST. One row per worker: transport, hotel, price, limit, status. Read live from each
 * worker's ONE trip (GET /api/booking/group/list — computed on the server, never stored), every 6 s. The organiser's list goes in
 * here too: a .csv / .xlsx file, a photo of the list, or pasted text (POST /api/booking/group/upload); unclear rows come back as ONE
 * question.
 */
import { useEffect, useState } from 'react'
import { bookingReq } from '@/lib/booking-client'

type Row = { member_id: string; name: string; grade?: string | null; home_city?: string | null; out?: string | null; back?: string | null
  transport?: string | null; hotel?: string | null; price_eur?: number | null; flight_eur?: number | null; hotel_eur_per_night?: number | null
  limit: { flight_return_eur?: number; hotel_night_eur?: number }; status: string; vault?: { passport: boolean; loyalty: string[] } }
type View = { movement?: { company?: string; destination?: string; starts_on?: string; ends_on?: string; hotel_area?: string }
  rows: Row[]; counts?: Record<string, number>; why?: string }

const TONE: Record<string, string> = { 'over limit': '#b42318', 'needs vault': '#b54708', planned: '#175cd3', booked: '#067647',
  cancelled: '#667085', 'not planned': '#667085' }
const eur = (n?: number | null) => (typeof n === 'number' ? `€${Math.round(n)}` : '—')

export default function GroupPage() {
  const [v, setV] = useState<View | null>(null)
  const [text, setText] = useState('')
  const [said, setSaid] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [links, setLinks] = useState<{ name: string; link: string }[]>([])
  // Sasha 334 · a master-list action's card: AgAPI's read-backs + the Yes / No the server gives (sasha.yes_buttons — 330's one place)
  const [card, setCard] = useState<{ read_back_id: string; read_back: string[]; ask: string; choices: { title: string; route: string }[] } | null>(null)
  const [swapIn, setSwapIn] = useState('')
  const [swapOut, setSwapOut] = useState('')

  useEffect(() => {
    let off = false
    const pull = async () => {
      const r = await bookingReq('/api/booking/group/list').catch(() => null)
      if (!off && r?.ok) setV(r.json as unknown as View)
    }
    pull()
    const t = setInterval(pull, 6000)
    return () => { off = true; clearInterval(t) }
  }, [])

  const send = async (body: Record<string, unknown>) => {
    setBusy(true)
    const r = await bookingReq('/api/booking/group/upload', body, 60000).catch(() => null)
    setBusy(false)
    const j = (r?.json || {}) as { added?: number; ask?: string | null; why?: string; message?: string }
    setSaid(r?.ok ? `Added ${j.added ?? 0}.${j.ask ? ' ' + j.ask : ''}` : (j.why || j.message || 'That list couldn’t be read — try again.'))
  }
  const invite = async (who: string[] | null) => {   // Sasha 333 · each member's own secure page — never collected in chat
    setBusy(true)
    const r = await bookingReq('/api/booking/group/invite', { who }, 60000).catch(() => null)
    setBusy(false)
    const j = (r?.json || {}) as { emailed?: string[]; forward?: { name: string; link: string }[]; why?: string }
    setLinks(j.forward || [])
    setSaid(r?.ok ? `Emailed ${j.emailed?.length ?? 0}.${j.forward?.length ? ` ${j.forward.length} to forward below.` : ''}` : (j.why || 'Not sent — try again.'))
  }
  const act = async (action: 'book' | 'swap' | 'cancel', who: string[] | null, to?: string) => {
    setBusy(true); setCard(null)
    const r = await bookingReq('/api/booking/group/act', { action, who, to }, 120000).catch(() => null)
    setBusy(false)
    const j = (r?.json || {}) as Record<string, unknown>
    if (r?.ok && j.status === 'awaiting_yes' && Array.isArray(j.choices)) setCard(j as unknown as NonNullable<typeof card>)
    else setSaid(String(j.say || j.message || 'Nothing to do.'))
  }
  const answer = async (choice: string) => {   // once per card: the server holds the claim; a second tap finds nothing
    if (!card) return
    const id = card.read_back_id
    setCard(null); setBusy(true)
    const r = await bookingReq('/api/booking/group/confirm', { card: id, choice }, 300000).catch(() => null)
    setBusy(false)
    setSaid(String(((r?.json || {}) as { say?: string }).say || 'Done.'))
  }
  const invoice = async () => {
    const r = await bookingReq('/api/booking/group/invoice').catch(() => null)
    const link = ((r?.json || {}) as { link?: string }).link
    if (link) window.open(link, '_blank', 'noopener')
    else setSaid(String(((r?.json || {}) as { why?: string }).why || 'The invoice isn’t ready.'))
  }
  const onFile = (f: File | undefined) => {
    if (!f) return
    const rd = new FileReader()
    rd.onload = () => send({ name: f.name, media_type: f.type, content_base64: String(rd.result).split(',')[1] || '' })
    rd.readAsDataURL(f)
  }

  const mv = v?.movement
  return (
    <main style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 16px', fontFamily: 'system-ui, sans-serif', color: '#101828' }}>
      <h1 style={{ fontSize: 22, margin: '0 0 4px' }}>{mv?.company ? `${mv.company} → ${mv.destination}` : 'Group movement'}</h1>
      {mv && <p style={{ margin: '0 0 16px', color: '#475467' }}>{[mv.starts_on, mv.ends_on].filter(Boolean).join(' – ')}{mv.hotel_area ? ` · hotel ${mv.hotel_area}` : ''}</p>}
      {v?.counts && <p data-counts style={{ margin: '0 0 16px' }}>{Object.entries(v.counts).map(([s, n]) => `${n} ${s}`).join(' · ')}</p>}
      <section style={{ border: '1px solid #eaecf0', borderRadius: 12, padding: 12, marginBottom: 16 }}>
        <label style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Add the list — a spreadsheet, a photo of it, or paste it</label>
        <input type="file" accept=".csv,.xlsx,image/*" disabled={busy} onChange={e => onFile(e.target.files?.[0])} />
        <textarea value={text} onChange={e => setText(e.target.value)} placeholder="Name, home city, out, back, grade — one person per line"
          rows={3} style={{ display: 'block', width: '100%', marginTop: 8, boxSizing: 'border-box' }} />
        <button type="button" disabled={busy || !text.trim()} onClick={() => send({ text })} style={{ marginTop: 8 }}>Add these</button>
        {said && <p data-upload-said style={{ whiteSpace: 'pre-line', marginTop: 8 }}>{said}</p>}
        <button type="button" disabled={busy || !v?.rows?.length} onClick={() => invite(null)} style={{ marginTop: 8 }}>Invite everyone to the vault</button>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          <button type="button" disabled={busy} onClick={() => act('book', null)}>Book all planned</button>
          <input value={swapOut} onChange={e => setSwapOut(e.target.value)} placeholder="Swap… (who leaves)" />
          <input value={swapIn} onChange={e => setSwapIn(e.target.value)} placeholder="for… (who comes)" />
          <button type="button" disabled={busy || !swapOut || !swapIn} onClick={() => act('swap', [swapOut], swapIn)}>Swap</button>
          <button type="button" onClick={invoice}>The invoice</button>
        </div>
        {card && <div data-group-card style={{ border: '1px solid #d0d5dd', borderRadius: 12, padding: 12, marginTop: 10 }}>
          {card.read_back.map((l, i) => <div key={i} style={{ fontSize: 14 }}>{l || '\u00a0'}</div>)}
          <p style={{ fontWeight: 600 }}>{card.ask}</p>
          {card.choices.map(c => <button key={c.route} type="button" disabled={busy} onClick={() => answer(c.route)} style={{ marginRight: 8 }}>{c.title}</button>)}
        </div>}
        {links.length > 0 && <ul data-forward>{links.map(l => <li key={l.link}>{l.name}: <a href={l.link}>their secure link</a></li>)}</ul>}
      </section>
      {!v ? <p>Loading…</p> : v.why ? <p>{v.why}</p> : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead><tr>{['Name', 'Grade', 'From', 'Transport', 'Hotel', 'Price', 'Limit', 'Vault', 'Status'].map(h =>
              <th key={h} style={{ textAlign: 'left', borderBottom: '1px solid #eaecf0', padding: '6px 8px' }}>{h}</th>)}</tr></thead>
            <tbody>{v.rows.map(r => (
              <tr key={r.member_id} data-status={r.status}>
                <td style={{ padding: '6px 8px' }}>{r.name}</td>
                <td style={{ padding: '6px 8px' }}>{r.grade || '—'}</td>
                <td style={{ padding: '6px 8px' }}>{r.home_city || '—'}</td>
                <td style={{ padding: '6px 8px' }}>{r.transport || '—'}</td>
                <td style={{ padding: '6px 8px' }}>{r.hotel ? `${r.hotel}${r.hotel_eur_per_night ? ` (${eur(r.hotel_eur_per_night)}/night, est.)` : ''}` : '—'}</td>
                <td style={{ padding: '6px 8px' }}>{eur(r.price_eur)}</td>
                <td style={{ padding: '6px 8px' }}>{[r.limit.flight_return_eur && `flight ≤ ${eur(r.limit.flight_return_eur)}`,
                  r.limit.hotel_night_eur && `hotel ≤ ${eur(r.limit.hotel_night_eur)}/night`].filter(Boolean).join(' · ') || '—'}</td>
                <td style={{ padding: '6px 8px' }} data-vault>{r.vault?.passport ? 'Passport ✓' : 'Passport missing'}{r.vault?.loyalty?.length ? ` · ${r.vault.loyalty.map(x => `${x} ✓`).join(' · ')}` : ''}
                  {!r.vault?.passport && <button type="button" disabled={busy} onClick={() => invite([r.member_id])} style={{ marginLeft: 6 }}>Invite</button>}
                  {r.vault?.passport && r.status !== 'booked' && r.status !== 'cancelled' && <button type="button" disabled={busy} onClick={() => act('book', [r.name])} style={{ marginLeft: 6 }}>Book</button>}
                  {r.status === 'booked' && <button type="button" disabled={busy} onClick={() => act('cancel', [r.name])} style={{ marginLeft: 6 }}>Cancel</button>}</td>
                <td style={{ padding: '6px 8px', color: TONE[r.status] || '#101828', fontWeight: 600 }}>{r.status}</td>
              </tr>))}</tbody>
          </table>
        </div>)}
    </main>)
}
