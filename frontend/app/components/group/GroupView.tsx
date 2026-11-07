'use client'
/**
 * Sasha 358 · THE GROUP VIEW — one component over THE GROUP ENGINE (backend booking_signer/groups.py: the company's roster + each trip's
 * selection, changed only by create_trip and set_on_trip). /group renders it; S2's and /next's group tab will render the same (Sasha 359).
 * It holds no logic of its own: it shows GET /api/booking/group/state and sends each press to the engine's doors, saying their answer.
 *
 *   NEW TRIP (no trip open, or "New trip"): the roster → where, dates, hotel area → tick who's going (or upload a list: onto the roster,
 *            ticked) → [Go] (POST /create: makes it, puts them on, plans each from their own home airport).
 *   MANAGE   (a trip open): who's on it FIRST (status, price, passport), each with its switch (the record itself: off → said; booked →
 *            Cancel offered); then the roster's others (a switch puts them on) and someone new (onto the roster AND the trip, said).
 *
 * Every press answers (lib/outcome — Sasha 346–348): nothing is greyed out, a press while another runs is told so, a lost request is said.
 */
import { useCallback, useEffect, useState } from 'react'
import { bookingReq } from '@/lib/booking-client'
import { heard as heardWords, failed, observe, stillGoing, toConsole } from '@/lib/outcome'
import { T, TONE, page, card as cardS, field, btn, btn2, small } from '@/lib/group-theme'

type NextAct = { id: string; label: string; say?: string; tool?: string; args?: { who?: string[]; over_limit_ok?: boolean } }
type Person = { id: string; name: string; grade?: string | null; role?: string | null; home_airport?: string | null; home_city?: string | null
  email?: string | null; phone?: string | null; vault?: { passport: boolean }; on: boolean; status?: string | null }
type Row = { member_id: string; person_id?: string; name: string; grade?: string | null; role?: string | null; home_city?: string | null
  home_airport?: string | null; transport?: string | null; hotel?: string | null; price_eur?: number | null; hotel_eur_per_night?: number | null
  status: string; vault?: { passport: boolean; loyalty: string[] }; actions?: NextAct[] }
type Trip = { id: string; destination: string; starts_on?: string | null; ends_on?: string | null; people?: number; open?: boolean }
type State = { company?: { id: string; name: string } | null; roster: Person[]; trips: Trip[]
  trip: { id: string; company?: string; destination: string; starts_on?: string | null; ends_on?: string | null; hotel_area?: string | null } | null
  list: { rows: Row[]; counts?: Record<string, number>; actions?: NextAct[] } }
type Res = Awaited<ReturnType<typeof bookingReq>>
type Card = { read_back_id: string; read_back: string[]; ask: string; choices: { title: string; route: string }[] }
type Tap = { label?: string; say?: string; act?: { action: 'book' | 'swap'; who: string[]; to?: string; over_ok: boolean }; invite?: string[] }

const eur = (n?: number | null) => (typeof n === 'number' ? `€${Math.round(n)}` : '—')
const BLANK = { name: '', role: '', grade: '', home_airport: '', home_city: '', email: '', phone: '' }
const NEW_FIELDS: [keyof typeof BLANK, string, number][] = [['name', 'Name', 170], ['role', 'Role / department', 140], ['grade', 'Grade', 90],
  ['home_airport', 'Home airport (MAD)', 130], ['home_city', 'Home city', 120], ['email', 'Email', 180], ['phone', 'Phone (+34…)', 120]]
const td = { padding: '6px 8px' }

/** a switch is the record: on = this person is on this trip (never a label) */
function Switch({ on, name, onPress }: { on: boolean; name: string; onPress: () => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={`${name} on this trip`} data-switch={on ? 'on' : 'off'} onClick={onPress}
      style={{ width: 44, height: 24, borderRadius: 999, border: `1px solid ${T.border}`, background: on ? T.booked : T.field, position: 'relative', cursor: 'pointer', padding: 0 }}>
      <span style={{ position: 'absolute', top: 2, left: on ? 22 : 2, width: 18, height: 18, borderRadius: 999, background: on ? T.bg : T.muted }} />
    </button>)
}

export default function GroupView() {
  const [st, setSt] = useState<State | null>(null)
  const [fresh, setFresh] = useState(false)   // "New trip" pressed while a trip is open
  const [said, setSaid] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [missing, setMissing] = useState<string[]>([])
  // NEW TRIP
  const [trip, setTrip] = useState({ company: '', destination: '', starts_on: '', ends_on: '', hotel_area: '' })
  const [ticked, setTicked] = useState<string[]>([])
  const [text, setText] = useState('')
  // someone new, a roster edit, documents
  const [draft, setDraft] = useState({ ...BLANK })
  const [edit, setEdit] = useState<string | null>(null)
  const [ed, setEd] = useState<Record<string, string>>({})
  const [docs, setDocs] = useState<{ id: string; link: string } | null>(null)
  // the list's actions (Sasha 334–352): AgAPI's card, held taps, moved fares, the invoice, forwarded vault links, a swap
  const [card, setCard] = useState<Card | null>(null)
  const [queue, setQueue] = useState<Card[]>([])
  const [taps, setTaps] = useState<Tap[]>([])
  const [offers, setOffers] = useState<NextAct[]>([])   // what a switch offered instead (a booked person: Cancel)
  const [invoiceLink, setInvoiceLink] = useState<string | null>(null)
  const [links, setLinks] = useState<{ name: string; link: string }[]>([])
  const [swap, setSwap] = useState({ out: '', in: '', city: '', grade: '' })

  const pull = useCallback(async () => {
    const r = await bookingReq('/api/booking/group/state')
    if (!r.ok) throw new Error(String(r.json.message || r.json.rule || r.status))
    setSt(r.json as unknown as State)
  }, [])
  useEffect(() => {
    observe(pull(), 'Reading the group', toConsole)
    bookingReq('/api/booking/group/waiting').then(r => {   // Sasha 340 · a moved fare's card survives a reload
      const re = ((r?.json || {}) as { reasked?: Card[] }).reasked || []
      if (re.length) { setCard(re[0]); setQueue(re.slice(1)) }
    }).catch(e => setSaid(failed('Reading the cards waiting for a yes', e)))
    const t = setInterval(() => observe(pull(), 'Reading the group', toConsole), 6000)
    return () => clearInterval(t)
  }, [pull])

  // every answer through the ONE reader: the server's words, else what happened to the request; the fields it named are marked
  const heard = (name: string, r: Res | null): Record<string, unknown> => {
    const j = (r?.json || {}) as Record<string, unknown>
    setMissing(Array.isArray(j.missing) ? (j.missing as string[]) : [])
    setSaid(heardWords(name, r))
    return j
  }
  // a press while another runs is TOLD so; every press ends in words (its answer, or what went wrong) and a fresh read of the record
  const press = (name: string, fn: () => Promise<unknown>) => () => {
    if (busy) { setSaid(stillGoing(busy, name)); return }
    setBusy(name); setSaid(`${name}…`); setInvoiceLink(null); setOffers([])
    observe(fn().finally(() => { setBusy(null); observe(pull(), 'Reading the group again', setSaid) }), name, setSaid)
  }
  const post = async (name: string, path: string, body: Record<string, unknown>, timeout = 60000) =>
    heard(name, await bookingReq(path, body, timeout).catch(() => null))

  // ── the engine's doors ──
  const tick = (ids: unknown) => { if (Array.isArray(ids)) setTicked(t => Array.from(new Set([...t, ...(ids as string[])]))) }
  const go = async () => {
    const j = await post('Go', '/api/booking/group/create', { ...trip, company: trip.company || undefined, who: ticked }, 120000)
    if (j.done) { setTicked([]); setFresh(false); setTrip({ company: '', destination: '', starts_on: '', ends_on: '', hotel_area: '' }) }
  }
  const flip = async (p: { id: string; on: boolean }) => {
    const j = await post('On this trip', '/api/booking/group/switch', { person: p.id, on: !p.on, trip: st?.trip?.id })
    setOffers(Array.isArray(j.actions) ? (j.actions as NextAct[]) : [])   // a booked person: Cancel offered, never taken off
  }
  const upload = async (body: Record<string, unknown>) => {
    const j = await post('Add these', '/api/booking/group/upload', { ...body, on_trip: !newTrip, company: trip.company || undefined })
    if (newTrip) tick(j.people)   // a new trip: onto the roster, ticked for [Go] — never onto a trip
    if (j.done) setText('')
  }
  const addNew = async () => {
    const j = await post('Add', '/api/booking/group/people', { rows: [Object.fromEntries(Object.entries(draft).filter(([, v]) => v.trim()))],
      company: trip.company || undefined, on_trip: !newTrip, trip: st?.trip?.id })
    if (j.done) { setDraft({ ...BLANK }); if (newTrip) tick(j.people) }
  }
  const save = async (id: string) => {
    const j = await post('Save', `/api/booking/group/people/${id}`, ed)
    if (j.done) { setEdit(null); setEd({}) }
  }
  const documents = async (id: string) => {
    const j = await post('Documents', `/api/booking/group/people/${id}/documents`, {})
    if (typeof j.link === 'string') setDocs({ id, link: j.link })
  }
  const openTrip = async (id: string) => {
    await post('Open this trip', '/api/booking/group/open', { trip: id })
    setFresh(false); setCard(null); setQueue([]); setTaps([]); setLinks([])
  }
  const readFile = (f: File) => new Promise<string>((ok, bad) => {
    const rd = new FileReader()
    rd.onerror = () => bad(new Error('that file couldn’t be read'))
    rd.onload = () => ok(String(rd.result).split(',')[1] || '')
    rd.readAsDataURL(f)
  })
  const onFile = async (f: File | undefined) => {
    if (!f) { setSaid('Add these needs a file — choose a .csv, an .xlsx or a photo of the list.'); return }
    await upload({ name: f.name, media_type: f.type, content_base64: await readFile(f) })
  }

  // ── the list's actions (unchanged since 334–352): ONE card, the book job followed, the invoice said, the vault invites ──
  const show = (j: Record<string, unknown>) => {
    if (j.status === 'awaiting_yes' && Array.isArray(j.choices)) setCard(j as unknown as Card)
    const re = (Array.isArray(j.reasked) ? j.reasked : []) as Card[]
    if (re.length) { setCard(re[0]); setQueue(re.slice(1)) }
    if (j.status === 'awaiting_yes') setSaid(Array.isArray(j.taps) && j.taps.length ? 'Some are held — see below the card.' : 'Read the card, then Yes or No.')
    else heard('That', { ok: true, status: 200, json: j })
    if (Array.isArray(j.taps)) setTaps(j.taps as Tap[])
    if (Array.isArray(j.links)) setLinks(j.links as { name: string; link: string }[])
  }
  const follow = async () => {
    for (let i = 0; i < 300; i++) {
      const r = await bookingReq('/api/booking/group/job').catch(() => null)
      const j = (r?.json || {}) as { state?: string; say?: string; result?: Record<string, unknown> }
      if (r?.ok && j.state === 'ready' && j.result) { show(j.result); return }
      if (r?.ok && j.state === 'failed') { setSaid(j.say || 'The read-backs couldn’t be prepared — nothing was booked. Try again.'); return }
      if (r?.ok && j.say) setSaid(j.say)
      await new Promise(res => setTimeout(res, 2000))
    }
    setSaid('Still preparing — this page stopped waiting. Nothing is booked; reload to see the card.')
  }
  const act = async (action: 'book' | 'swap' | 'cancel', who: string[] | null, to?: string, more: Record<string, unknown> = {}) => {
    const name = { book: 'Book', swap: 'Swap', cancel: 'Cancel' }[action]
    setCard(null); setTaps([])
    const r = await bookingReq('/api/booking/group/act', { action, who, to, ...more }, 120000).catch(() => null)
    const j = (r?.json || {}) as Record<string, unknown>
    if (!r?.ok) { heard(name, r); return }
    if (j.status === 'preparing') { if (j.say) setSaid(String(j.say)); if (Array.isArray(j.taps)) setTaps(j.taps as Tap[]); return follow() }
    show(j)
  }
  const answer = async (choice: string) => {
    if (!card) { setSaid('That card was already answered — the list shows what was done.'); return }
    const id = card.read_back_id
    setCard(null); setSaid(choice === 'group_yes' ? 'Booking…' : 'Saying no…')
    const r = await bookingReq('/api/booking/group/confirm', { card: id, choice }, 120000).catch(() => null)
    const j = (r?.json || {}) as Record<string, unknown>
    if (!r?.ok) { heard('Your answer', r); return }
    if (j.status === 'booking') { if (j.say) setSaid(String(j.say)); return follow() }
    if (Array.isArray(j.reasked) && j.reasked.length) return show(j)
    heard('Your answer', r)
    if (queue.length) { setCard(queue[0]); setQueue(queue.slice(1)) }
  }
  const invite = async (who: string[] | null) => {
    const j = await post('Invite', '/api/booking/group/invite', { who })
    setLinks(((j as { forward?: { name: string; link: string }[] }).forward) || [])
  }
  const invoice = async () => {
    const r = await bookingReq('/api/booking/group/invoice').catch(() => null)
    const link = (heard('The invoice', r) as { link?: string }).link
    setInvoiceLink(link || null)
  }
  const doNext = (a: NextAct) => {
    if (a.tool === 'group_book') return act('book', a.args?.who || null, undefined, a.args?.over_limit_ok ? { over_ok: true } : {})
    if (a.tool === 'group_cancel') return act('cancel', a.args?.who || null)
    if (a.tool === 'group_invite_vault') return invite(a.args?.who || null)
    if (a.tool === 'group_invoice') return invoice()
    return Promise.resolve(setSaid(`${a.label}: this page can't do that yet — ask Sasha in the chat.`))
  }

  const mark = (f: string) => (missing.includes(f) ? { ...field, borderColor: T.vault, boxShadow: `0 0 0 1px ${T.vault}` } : field)
  const newTrip = !st?.trip || fresh
  const onTrip = (st?.roster || []).filter(p => p.on)
  const others = (st?.roster || []).filter(p => !p.on)
  const rowOf = (pid: string) => (st?.list.rows || []).find(r => r.person_id === pid)

  const personCells = (p: Person) => edit === p.id ? <>
    {(['name', 'role', 'grade', 'home_airport', 'home_city', 'email'] as const).map(k => (
      <td key={k} style={{ padding: 4 }}><input aria-label={k} value={ed[k] ?? (p[k] || '')} onChange={e => setEd({ ...ed, [k]: e.target.value })} style={{ ...field, width: 120 }} /></td>))}
    <td style={td}><button type="button" data-save={p.id} onClick={press('Save', () => save(p.id))} style={small}>Save</button></td></> : <>
    <td style={td}>{p.name}</td><td style={td}>{p.role || '—'}</td><td style={td}>{p.grade || '—'}</td>
    <td style={td}>{p.home_airport || p.home_city || '—'}</td>
    <td style={td} data-passport={p.vault?.passport ? '1' : '0'}>{p.vault?.passport ? 'Passport ✓' : 'Passport missing'}</td>
    <td style={{ ...td, whiteSpace: 'nowrap' }}>
      <button type="button" data-edit={p.id} onClick={press('Edit', async () => { setEdit(p.id); setEd({}); setSaid(`Editing ${p.name} — change what’s needed, then Save.`) })} style={small}>Edit</button>{' '}
      <button type="button" data-documents={p.id} onClick={press('Documents', () => documents(p.id))} style={small}>Documents</button></td></>

  const head = (cols: string[]) => <thead><tr>{cols.map(h => <th key={h} style={{ textAlign: 'left', borderBottom: `1px solid ${T.border}`, padding: '6px 8px', color: T.muted }}>{h}</th>)}</tr></thead>

  const addSomeone = (
    <div data-person-add style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '8px 0' }}>
      {NEW_FIELDS.map(([k, label, w]) => <input key={k} aria-label={label} placeholder={label} value={draft[k]} onChange={e => setDraft({ ...draft, [k]: e.target.value })} style={{ ...field, width: w }} />)}
      <button type="button" data-add-new onClick={press('Add', addNew)} style={btn2}>{newTrip ? 'Add to the roster (ticked)' : 'Add to the roster and this trip'}</button>
    </div>)

  return (
    <main style={{ ...page, maxWidth: 1100, margin: '0 auto', padding: '24px 16px' }}>
      <h1 style={{ fontSize: 22, margin: '0 0 4px' }}>{newTrip ? 'New trip' : `${st?.trip?.company || ''} → ${st?.trip?.destination}`}{st?.company ? ` · ${st.company.name}` : ''}</h1>
      {!newTrip && st?.trip && <p style={{ margin: '0 0 12px', color: T.muted }}>{[st.trip.starts_on, st.trip.ends_on].filter(Boolean).join(' – ')}{st.trip.hotel_area ? ` · hotel ${st.trip.hotel_area}` : ''}</p>}
      <p data-trips style={{ margin: '0 0 12px', display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <span style={{ color: T.muted }}>Your trips:</span>
        {(st?.trips || []).map(t => t.open && !fresh
          ? <span key={t.id} data-trip-open={t.id} style={{ ...small, fontWeight: 700 }}>{t.destination} {String(t.starts_on || '').slice(0, 10)} · {t.people ?? 0} · open</span>
          : <button key={t.id} type="button" data-trip={t.id} onClick={press('Open this trip', () => openTrip(t.id))} style={small}>{t.destination} {String(t.starts_on || '').slice(0, 10)} · {t.people ?? 0}</button>)}
        <button type="button" data-new-trip onClick={press('New trip', async () => { setFresh(true); setTicked([]); setSaid('A new trip: where and when, then tick who’s going (or add them) and press Go. Nothing is made until Go.') })} style={small}>New trip</button>
      </p>
      {said && <p data-said role="status" aria-live="polite" style={{ whiteSpace: 'pre-line', margin: '6px 0 12px' }}>{said}</p>}
      {offers.length > 0 && <p data-offers style={{ display: 'flex', gap: 8 }}>{offers.map(a => <button key={a.id} type="button" onClick={press(a.label, () => doNext(a))} style={btn2}>{a.label}</button>)}</p>}
      {docs && <p data-docs-link><a href={docs.link} target="_blank" rel="noopener" style={{ color: T.link, textDecoration: 'underline' }}>Open their vault page</a><span style={{ color: T.muted }}> — or forward it to them</span></p>}
      {st === null ? <p>Reading the group…</p> : newTrip ? (
        <section data-new style={{ ...cardS, marginBottom: 16 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {!st.company && <input aria-label="company" placeholder="Company" value={trip.company} onChange={e => setTrip({ ...trip, company: e.target.value })} style={{ ...field, width: 200 }} />}
            <input aria-label="where" placeholder="Where (Lisbon)" value={trip.destination} onChange={e => setTrip({ ...trip, destination: e.target.value })} style={{ ...mark('where'), width: 180 }} />
            <input aria-label="out" type="date" value={trip.starts_on} onChange={e => setTrip({ ...trip, starts_on: e.target.value })} style={field} />
            <input aria-label="back" type="date" value={trip.ends_on} onChange={e => setTrip({ ...trip, ends_on: e.target.value })} style={field} />
            <input aria-label="hotel area" placeholder="Hotel area (near the client)" value={trip.hotel_area} onChange={e => setTrip({ ...trip, hotel_area: e.target.value })} style={{ ...field, width: 240 }} />
          </div>
          <h2 style={{ fontSize: 16, margin: '14px 0 4px' }}>Who’s going — tick them ({ticked.length} ticked)</h2>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            {head(['Going', 'Name', 'Role', 'Grade', 'From', 'Passport', ''])}
            <tbody>{st.roster.map(p => <tr key={p.id} data-person={p.id} style={{ borderBottom: `1px solid ${T.second}` }}>
              <td style={td}><input type="checkbox" aria-label={`${p.name} is going`} data-tick={p.id} checked={ticked.includes(p.id)}
                onChange={e => setTicked(t => (e.target.checked ? [...t, p.id] : t.filter(x => x !== p.id)))} /></td>{personCells(p)}</tr>)}</tbody>
          </table></div>
          {!st.roster.length && <p style={{ color: T.muted }}>Your roster is empty — add your people below (each once; every trip picks from them).</p>}
          <p style={{ fontWeight: 600, margin: '12px 0 4px' }}>Add people — a spreadsheet, a photo of the list, or paste it (they go on your roster, ticked)</p>
          <input type="file" accept=".csv,.xlsx,image/*" onChange={e => press('Add these', () => onFile(e.target.files?.[0]))()} style={{ color: T.text }} />
          <textarea value={text} onChange={e => setText(e.target.value)} placeholder="Name, home city, role, grade — one person per line" rows={3} style={{ ...field, display: 'block', width: '100%', marginTop: 8 }} />
          <button type="button" onClick={press('Add these', () => upload({ text }))} style={{ ...btn2, marginTop: 8 }}>Add these</button>
          {addSomeone}
          <button type="button" data-go onClick={press('Go', go)} style={{ ...btn, marginTop: 8 }}>Go — make the trip with {ticked.length} {ticked.length === 1 ? 'person' : 'people'}</button>
        </section>) : (<>
        <section data-on-trip style={{ ...cardS, marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, margin: '0 0 4px' }}>On this trip ({onTrip.length}){st.list.counts ? ` — ${Object.entries(st.list.counts).map(([s, n]) => `${n} ${s}`).join(' · ')}` : ''}</h2>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            {head(['On', 'Name', 'Role', 'Grade', 'From', 'Transport', 'Hotel', 'Price', 'Passport', 'Status', ''])}
            <tbody>{onTrip.map(p => { const r = rowOf(p.id); return (
              <tr key={p.id} data-person={p.id} data-status={r?.status} style={{ borderBottom: `1px solid ${T.second}` }}>
                <td style={td}><Switch on name={p.name} onPress={press('On this trip', () => flip(p))} /></td>
                <td style={td}>{p.name}</td><td style={td}>{p.role || '—'}</td><td style={td}>{p.grade || '—'}</td>
                <td style={td}>{p.home_airport || p.home_city || '—'}</td>
                <td style={td}>{r?.transport || '—'}</td>
                <td style={td}>{r?.hotel ? `${r.hotel}${r.hotel_eur_per_night ? ` (${eur(r.hotel_eur_per_night)}/night, est.)` : ''}` : '—'}</td>
                <td style={td}>{eur(r?.price_eur)}</td>
                <td style={td} data-vault>{r?.vault?.passport ? 'Passport ✓' : 'Passport missing'}</td>
                <td style={{ ...td, color: TONE[r?.status || ''] || T.text, fontWeight: 600 }}>{r?.status || 'not planned'}</td>
                <td style={{ ...td, whiteSpace: 'nowrap' }}>{(r?.actions || []).map(a => <button key={a.id} type="button" data-next={a.id} onClick={press(a.label, () => doNext(a))} style={{ ...small, marginRight: 4 }}>{a.label}</button>)}
                  <button type="button" data-documents={p.id} onClick={press('Documents', () => documents(p.id))} style={small}>Documents</button></td>
              </tr>) })}</tbody>
          </table></div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
            {(st.list.actions || []).map(a => <button key={a.id} type="button" data-next={a.id} onClick={press(a.label, () => doNext(a))} style={a.id === 'book_all' ? btn : btn2}>{a.label}</button>)}
          </div>
          {invoiceLink && <p data-invoice-link><a href={invoiceLink} target="_blank" rel="noopener" style={{ color: T.link, textDecoration: 'underline' }}>Open the invoice</a></p>}
          {taps.length > 0 && <div data-taps style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
            {taps.map((t, i) => <span key={i} style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
              {t.say && <span style={{ color: T.muted }}>{t.say}</span>}
              {t.act ? <button type="button" style={btn} onClick={press(t.label || 'Book anyway', () => act(t.act!.action, t.act!.who, t.act!.to, { over_ok: true }))}>{t.label}</button>
                : t.invite ? <button type="button" style={btn2} onClick={press('Invite', () => invite(t.invite!))}>{t.label}</button> : null}</span>)}
          </div>}
          {card && <div data-group-card style={{ ...cardS, background: T.bg, marginTop: 10 }}>
            {card.read_back.map((l, i) => <div key={i} style={{ fontSize: 14 }}>{l || ' '}</div>)}
            <p style={{ fontWeight: 600 }}>{card.ask}</p>
            {card.choices.map((c, i) => <button key={c.route} type="button" onClick={press(c.title, () => answer(c.route))} style={{ ...(i === 0 ? btn : btn2), marginRight: 8 }}>{c.title}</button>)}
          </div>}
          {links.length > 0 && <ul data-forward>{links.map(l => <li key={l.link}>{l.name}: <a href={l.link} style={{ color: T.link, textDecoration: 'underline' }}>their secure link</a></li>)}</ul>}
          <div data-swap style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10, alignItems: 'center' }}>
            <input value={swap.out} onChange={e => setSwap({ ...swap, out: e.target.value })} placeholder="Swap… (who leaves)" aria-label="who leaves" style={mark('who leaves')} />
            <input value={swap.in} onChange={e => setSwap({ ...swap, in: e.target.value })} placeholder="for… (who comes)" aria-label="who comes" style={mark('who comes')} />
            <input value={swap.city} onChange={e => setSwap({ ...swap, city: e.target.value })} placeholder="their home city (if new)" aria-label="their home city" style={mark('their home city')} />
            <input value={swap.grade} onChange={e => setSwap({ ...swap, grade: e.target.value })} placeholder="grade (if new)" aria-label="grade" style={{ ...field, width: 130 }} />
            <button type="button" onClick={press('Swap', () => act('swap', [swap.out.trim()], swap.in.trim(), { to_city: swap.city.trim(), to_grade: swap.grade.trim() }))} style={btn2}>Swap</button>
          </div>
        </section>
        <section data-roster style={{ ...cardS, marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, margin: '0 0 4px' }}>Add from your roster ({others.length} not on this trip)</h2>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            {head(['On', 'Name', 'Role', 'Grade', 'From', 'Passport', ''])}
            <tbody>{others.map(p => <tr key={p.id} data-person={p.id} style={{ borderBottom: `1px solid ${T.second}` }}>
              <td style={td}><Switch on={false} name={p.name} onPress={press('On this trip', () => flip(p))} /></td>{personCells(p)}</tr>)}</tbody>
          </table></div>
          <p style={{ fontWeight: 600, margin: '12px 0 4px' }}>Someone new — onto your roster and this trip</p>
          {addSomeone}
        </section></>)}
    </main>)
}
