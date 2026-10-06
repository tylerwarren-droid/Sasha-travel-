'use client'

/**
 * Sasha 158 · THE LADDER in the chat, said simply: their own booking form, else their email (with "no reply → I'll call",
 * under the same yes), the route chosen by Sasha, never explained. One sentence before, the exact words to be sent behind
 * "See exactly what I'll send", one yes, one sentence after. A no-slot request (a tattoo, custom work) is a request for a
 * date and a quote. The server keeps every rule (the read-back's hash, the AI disclosure, the caps); this only says less.
 */
import { useEffect, useState } from 'react'
import { bookingReq, contactReq, refusal } from '@/lib/booking-client'
import { setPendingYes } from '@/lib/chat-booking-bus'

type Route = 'form' | 'email'
type Phase = { k: 'details' } | { k: 'preparing' } | { k: 'readback'; id: string; sha: string; lines: string[]; sentence: string }
  | { k: 'sending' } | { k: 'done'; say: string } | { k: 'stopped'; say: string }

const NO_SLOT = /\b(tattoo|piercing|custom|commission|portrait|design|tailor|alteration|repair|restoration|engraving|mural|bespoke|quote)/i
const pad = (n: number) => String(n).padStart(2, '0')
/** the server's reason without its rule code ("form_phone_missing — the form needs…" → "the form needs…") */
const plain = (why: string) => why.replace(/^[a-z]+(?:_[a-z0-9]+)+\s*[—:-]\s*/i, '').replace(/[.]+$/, '')
const dayWords = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })

export function ChatBookingDo({ route, readId, venue, what, openAt, draft, line }: {
  route: Route; readId: string; venue: string; what: string; openAt: string | null
  /** Sasha 161 · the route's one plain line (the server's), said instead of a sentence of our own */
  line?: string | null
  draft: { when?: { at?: string }; how_many?: { count?: number } } | null
}) {
  const at = openAt || draft?.when?.at || ''
  const quote = route === 'email' && NO_SLOT.test(what)
  const [d, setD] = useState({ date: at.slice(0, 10), time: at.slice(11, 16), party: draft?.how_many?.count ?? 2, name: '', phone: '',
    want: what, dates: '' })
  const [p, setP] = useState<Phase>({ k: 'details' })
  const [ready, setReady] = useState(false)
  const [named0, setNamed0] = useState(false)   // a saved name: never asked again
  const [phoned0, setPhoned0] = useState(false)  // a saved mobile: never asked again (their form needs one)
  useEffect(() => {
    let off = false
    contactReq('GET').then((r) => {
      if (off) return
      const c = (r.json.contact ?? null) as { name?: string; mobile_e164?: string } | null
      setD((x) => ({ ...x, name: c?.name ?? '', phone: c?.mobile_e164 ?? '' }))
      setNamed0(!!c?.name)
      setPhoned0(!!c?.mobile_e164)
      setReady(true)
    }).catch(() => { if (!off) setReady(true) })
    return () => { off = true }
  }, [])
  const needPhone = route === 'form' && !phoned0
  const complete = !!d.name.trim() && (!needPhone || /^\+?\d[\d\s().-]{6,}$/.test(d.phone.trim())) && (quote ? d.want.trim().length >= 3 : !!(d.date && d.time && d.party))
  // everything known already: no form to fill — straight to the read-back
  useEffect(() => { if (ready && complete && p.k === 'details' && (quote ? false : !!at)) prepare() }, [ready])  // eslint-disable-line react-hooks/exhaustive-deps

  async function prepare() {
    setP({ k: 'preparing' })
    let r
    let sentence: string
    if (route === 'form') {
      const reservation = { schema: 'reservation/1', flow: 'book', where: {},
        who: { name: d.name.trim(), contact: d.phone ? { mobile_e164: d.phone.replace(/[\s().-]/g, '') } : {} },
        what: { activity: 'a table', activity_venue_lang: 'una mesa', category: 'restaurant' },
        when: { mode: 'at', at: `${d.date}T${d.time}` }, how_many: { count: d.party, unit: 'people' } }
      r = await bookingReq('/api/booking/forms', { read_id: readId, reservation })
      sentence = `I'll book ${venue} for ${d.party} on ${dayWords(d.date)} at ${d.time}.`
      if (r.ok) {
        const b = r.json.read_back as { lines: string[]; sha256: string }
        return setP({ k: 'readback', id: String(r.json.form_id), sha: b.sha256, lines: b.lines, sentence })
      }
    } else {
      r = await bookingReq('/api/booking/emails', quote
        ? { read_id: readId, name: d.name.trim(), quote: { what: d.want.trim(), dates: d.dates.trim() } }
        : { read_id: readId, date: d.date, time: d.time, party: d.party, name: d.name.trim(), auto_plan: true })
      sentence = quote ? `I'll send ${venue} your request and ask for a date and a quote.`
        : `I'll ask ${venue} for a table for ${d.party} on ${dayWords(d.date)} at ${d.time}.`
      if (r.ok) {
        const b = r.json.read_back as { lines: string[]; sha256: string }
        return setP({ k: 'readback', id: String(r.json.email_id), sha: b.sha256, lines: b.lines, sentence })
      }
    }
    setP({ k: 'stopped', say: `I couldn't — ${plain(refusal(r.json, r.status))}. Nothing was sent.` })
  }

  async function yes(said: string | null = null) {
    if (p.k !== 'readback') return
    const { id, sha } = p
    setP({ k: 'sending' })
    const approval = said ? { how: 'chat', said } : { how: 'button', said: null }
    const r = route === 'form'
      ? await bookingReq(`/api/booking/forms/${id}/send`, { read_back_sha256: sha, approval }, 120000)
      : await bookingReq(`/api/booking/emails/${id}/send`, { read_back_sha256: sha, approval }, 60000)
    if (!r.ok) return setP({ k: 'stopped', say: `It didn't go — ${plain(refusal(r.json, r.status))}. Nothing was sent.` })
    const reading = (r.json.reading ?? {}) as { result?: string }
    if (route === 'form' && reading.result === 'confirmed')
      return setP({ k: 'done', say: `Done — booked${r.json.booking_reference ? ` (their ref ${String(r.json.booking_reference)})` : ''}. It's in your itinerary.` })
    if (route === 'email' && r.json.status !== 'sent') return setP({ k: 'stopped', say: String(r.json.say ?? 'It was not sent.') })
    setP({ k: 'done', say: "Done — I've asked them and I'll confirm here as soon as they reply." })
  }

  // a typed "yes" in the chat answers the read-back, as the button does
  useEffect(() => {
    if (p.k !== 'readback') { return }
    setPendingYes((said) => { yes(said) })
    return () => setPendingYes(null)
  }, [p.k])  // eslint-disable-line react-hooks/exhaustive-deps

  const box = { background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.1)', borderRadius: 10, padding: 10, marginTop: 6 } as const
  const input = { background: 'rgba(0,0,0,.25)', color: 'inherit', border: '1px solid rgba(255,255,255,.15)', borderRadius: 6, padding: '4px 6px' } as const
  if (!ready || p.k === 'preparing') return <div style={{ opacity: 0.7 }}>One moment…</div>
  if (p.k === 'details') return (
    <div style={box}>
      {quote ? <>
        <div>What would you like {venue} to do?</div>
        <textarea value={d.want} onChange={(e) => setD({ ...d, want: e.target.value })} rows={3} style={{ ...input, width: '100%', marginTop: 4 }} />
        <input placeholder="Dates that suit you (optional)" value={d.dates} onChange={(e) => setD({ ...d, dates: e.target.value })} style={{ ...input, width: '100%', marginTop: 4 }} />
      </> : (at && d.date && d.time) ? null : <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <input type="date" value={d.date} onChange={(e) => setD({ ...d, date: e.target.value })} style={input} />
        <input type="time" value={d.time} onChange={(e) => setD({ ...d, time: e.target.value })} style={input} />
        <input type="number" min={1} max={20} value={d.party} onChange={(e) => setD({ ...d, party: Number(e.target.value) })} style={{ ...input, width: 56 }} /> people
      </div>}
      {!named0 && <div style={{ marginTop: 4 }}>Whose name should it be under?</div>}
      {!named0 && <input placeholder="Your name" value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} style={{ ...input, marginTop: 6 }} />}
      {needPhone && <div style={{ marginTop: 6 }}>And a mobile number they can reach you on?</div>}
      {needPhone && <input placeholder="+34 600 000 000" type="tel" value={d.phone} onChange={(e) => setD({ ...d, phone: e.target.value })} style={{ ...input, marginTop: 4 }} />}
      <div style={{ marginTop: 8 }}><button className="price" disabled={!complete} onClick={() => { prepare() }}>Continue</button></div>
    </div>
  )
  // Sasha 169 · the founder's demo stand-in (SASHA_DEMO_STANDIN): said first, every time — the place picked is never contacted
  const standIn = / \(TEST stand-in\)$/.test(venue) ? venue.replace(/ \(TEST stand-in\)$/, '') : null
  if (p.k === 'readback') return (
    <div style={box}>
      {standIn && <div style={{ color: '#E8B923', marginBottom: 4 }}>🧪 TEST: {standIn} — our test venue stands in; {standIn} is not contacted.</div>}
      <div>{line || p.sentence}</div>
      {line ? <div style={{ fontSize: 12.5, opacity: 0.75 }}>{quote ? d.want : `${d.party} people · ${dayWords(d.date)} at ${d.time}`}</div> : null}
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button className="price" onClick={() => { yes() }}>{route === 'form' ? 'Book it' : 'Yes'}</button>
        <button className="viewlink" onClick={() => setP({ k: 'stopped', say: 'OK — nothing was sent.' })}>No</button>
      </div>
    </div>
  )
  if (p.k === 'sending') return <div style={{ opacity: 0.7 }}>Sending…</div>
  return <div style={box}>{p.say}</div>
}

/** the date as the inputs want it, for a pre-filled day ("tomorrow" etc. arrive as open_at) */
export const toInputs = (iso: string) => ({ date: iso.slice(0, 10), time: `${pad(Number(iso.slice(11, 13)))}:${iso.slice(14, 16)}` })
