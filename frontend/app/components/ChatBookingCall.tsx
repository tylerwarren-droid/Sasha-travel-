'use client'

/**
 * S-66 (EU) steps 7–9 · BOOKING BY PHONE INSIDE THE CHAT: the details asked once → the server's read-back, word for
 * word → the yes (a button, or a typed "yes" bound to THIS card's read-back hash) → the call → the result in the venue's
 * words → "it's in your itinerary", said only once /reservations returns the row. Rendered by ChatBooking after a read.
 *
 * Every sentence shown is the server's (`read_back.lines`, `say`, `status_words`) or built from the object the guest
 * filled in. A refusal is shown as the server said it — calls off, opted out, the 15-minute window — and nothing is
 * dialled. Nothing here decides an outcome: the recap check and every rule run on the server.
 */
import { useEffect, useRef, useState } from 'react'
import { approveCall, bookingReq, getCall, prepareCall, guestRefusal as refusal, reservations, type Rung, contactReq, type Consent, type Contact } from '@/lib/booking-client'
import { setPendingYes } from '@/lib/chat-booking-bus'
import { GatedButton } from '../booking-helper/GatedButton'
import ReceiptCard from './ReceiptCard'

type Draft = { parts?: { what?: { activity: string; activity_venue_lang: string; category: string }; when?: { mode: string; at?: string };
  how_many?: { count: number; unit: string }; flow?: string; who?: { name: string } } } | null
type Details = { activity: string; venueLang: string; category: string; date: string; time: string; ask: boolean; count: number;
  unit: string; duration: string; name: string; mobile: string }
type View = { call_id: string; status: string; outcome?: string | null; venue_words?: string | null; say?: string | null; read_by?: string | null }
type Phase =
  | { p: 'details' } | { p: 'preparing' } | { p: 'readback'; callId: string; lines: string[]; sha: string }
  | { p: 'placing'; lines: string[] } | { p: 'calling'; callId: string; say: string } | { p: 'result'; view: View; itinerary: string; receipt: string | null }
  | { p: 'refused'; words: string } | { p: 'not_now' }

const SLEEP = (ms: number) => new Promise((r) => setTimeout(r, ms))

export default function ChatBookingCall({ readId, country, phone, venue, draft, whatText, openAt, onContacted }: {
  readId: string; country: string | null; phone: Rung; venue: string; draft: Draft; whatText: string; openAt?: string | null
  /** Sasha 88 · told when a call is placed or scheduled, so the chat stops saying "nothing has been contacted" */
  onContacted?: (how: 'calling' | 'scheduled') => void }) {
  // Sasha 86 · pre-filled from THIS message only (its draft, else the day and time its cards were filtered by) — every
  // field visible and editable; nothing carried from an earlier request
  const parts = draft?.parts ?? {}
  const at = parts.when?.mode === 'at' && parts.when.at ? parts.when.at.split('T')
    : openAt && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(openAt) ? openAt.split('T') : ['', '']
  const [d, setD] = useState<Details>({
    activity: parts.what?.activity ?? whatText, venueLang: parts.what?.activity_venue_lang ?? '', category: parts.what?.category ?? 'other',
    date: at[0], time: at[1], ask: parts.when?.mode === 'venue_proposes', count: parts.how_many?.count ?? 1, unit: parts.how_many?.unit ?? 'people',
    duration: '', name: parts.who?.name ?? '', mobile: '' })
  const [langEdited, setLangEdited] = useState(false)
  const [phase, setPhase] = useState<Phase>({ p: 'details' })
  // S-62 step 5 · saved details: used if there are some; saved only with the consent sentence shown; deleted on request
  const [saved, setSaved] = useState<{ contact: Contact | null; consent: Consent } | { why: string } | null>(null)
  const [keep, setKeep] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  // Sasha 96 · booking is automatic from the guest's side: no form on the normal path — it is opened only to change a
  // detail, and ONE question is asked only when something essential is missing
  const [showForm, setShowForm] = useState(false)
  const [autoTried, setAutoTried] = useState(false)
  // Sasha 100 · the one question, and then the result, are brought into view as they appear
  const stepRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (['readback', 'calling', 'result', 'refused'].includes(phase.p)) stepRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [phase.p])
  useEffect(() => {
    let off = false
    ;(async () => {
      try {
        const r = await contactReq('GET')
        if (off) return
        if (!r.ok) { setSaved({ why: refusal(r.json, r.status) }); return }
        const got = r.json as { contact: Contact | null; consent: Consent }
        setSaved(got)
        if (got.contact) setD((x) => ({ ...x, name: x.name || got.contact!.name, mobile: x.mobile || got.contact!.mobile_e164 }))
      } catch (e) {
        if (!off) setSaved({ why: (e as Error).message })
      }
    })()
    return () => { off = true }
  }, [])

  async function forget() {
    try {
      const r = await contactReq('DELETE')
      setNote(r.ok ? String(r.json.say ?? 'Deleted.') : `Not deleted — ${refusal(r.json, r.status)}`)
      if (r.ok && saved && 'consent' in saved) setSaved({ ...saved, contact: null })
    } catch (e) {
      setNote(`Not deleted — ${(e as Error).message}`)
    }
  }

  // the activity worded in the venue's language, once — from the server's deterministic list (nothing invented)
  useEffect(() => {
    let off = false
    bookingReq('/api/booking/draft', { text: whatText, country: country ?? undefined }).then((r) => {
      const w = (r.json.parts as { what?: { activity: string; activity_venue_lang: string; category: string } } | undefined)?.what
      // Sasha 86 · the venue's language wins over the chat's English draft ("a table" → "una mesa"), unless the guest typed one
      if (!off && w) setD((x) => ({ ...x, activity: x.activity || w.activity, venueLang: langEdited ? x.venueLang : (w.activity_venue_lang || x.venueLang), category: w.category }))
    }).catch(() => { /* the field stays for the guest to fill */ })
    return () => { off = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- once per venue country; a later edit is the guest's
  }, [whatText, country])

  async function prepare() {
    setPhase({ p: 'preparing' })
    if (keep && saved && 'consent' in saved) {   // S-62 step 5 · saved under the exact sentence shown, or not at all — and said
      try {
        const r = await contactReq('PUT', { name: d.name, mobile: d.mobile, consent_version: saved.consent.version, consent_sha256: saved.consent.sha256 })
        setNote(r.ok ? 'Saved for next time.' : `Not saved — ${refusal(r.json, r.status)}`)
        if (r.ok) setSaved({ ...saved, contact: (r.json.contact as Contact) ?? null })
      } catch (e) {
        setNote(`Not saved — ${(e as Error).message}`)
      }
    }
    const reservation = {
      schema: 'reservation/1', flow: d.ask ? 'availability' : 'book',
      who: { name: d.name.trim(), ...(d.mobile.trim() ? { contact: { mobile_e164: d.mobile.trim() } } : {}) },
      what: { activity: d.activity.trim(), activity_venue_lang: d.venueLang.trim(), category: d.category },
      where: {}, when: d.ask ? { mode: 'venue_proposes' } : { mode: 'at', at: `${d.date}T${d.time}`, ...(Number(d.duration) > 0 ? { duration_min: Number(d.duration) } : {}) },
      how_many: { count: d.count, unit: d.unit },
    }
    const r = await prepareCall({ reservation, read_id: readId, ...(phone.fact_index !== null ? { fact_index: phone.fact_index } : {}) })
    if (!r.ok) { setPhase({ p: 'refused', words: `Not prepared — ${refusal(r.json, r.status)}. Nothing was dialled.` }); return }
    const rb = r.json.read_back as { lines: string[]; sha256: string }
    setPhase({ p: 'readback', callId: String(r.json.call_id), lines: rb.lines, sha: rb.sha256 })
  }

  async function approve(callId: string, sha: string, lines: string[], how: 'button' | 'chat', said: string | null) {
    setPendingYes(null)
    setPhase({ p: 'placing', lines })
    const r = await approveCall(callId, sha, { how, said })
    if (!r.ok) { setPhase({ p: 'refused', words: `Not called — ${refusal(r.json, r.status)}. Nothing was dialled.` }); return }
    if (r.json.status === 'scheduled') { onContacted?.('scheduled'); setPhase({ p: 'refused', words: String(r.json.say) }); return }
    if (r.json.status !== 'placed' && r.json.status !== 'uncertain') { setPhase({ p: 'refused', words: String(r.json.say ?? 'The call was not placed.') }); return }
    onContacted?.('calling')
    setPhase({ p: 'calling', callId, say: String(r.json.say ?? 'Calling now.') })
    for (let i = 0; i < 48; i++) {                       // every 10 s, up to 8 minutes (Bland's ceiling is 4)
      await SLEEP(10000)
      const g = await getCall(callId)
      if (!g.ok) continue
      const v = g.json as unknown as View
      if (v.status === 'placed' || v.status === 'placing') { setPhase({ p: 'calling', callId, say: `I'm on the phone to ${venue} now.` }); continue }
      // the itinerary line only from a row the server returns — never assumed
      const res = await reservations()
      const row = ((res.json.reservations ?? []) as Array<{ intent_id: string; what: string; venue: string; date: string | null; time: string | null; status_words: string; receipt: string | null }>)
        .find((x) => x.intent_id === callId)
      // Sasha 88 · the place by the name the guest chose it by, never the words they searched with; and its receipt
      setPhase({ p: 'result', view: v, receipt: row?.receipt ?? null, itinerary: row
        ? `It's in your itinerary: ${row.what} at ${venue}${row.date ? `, ${row.date}${row.time ? ` at ${row.time}` : ''}` : ''}. Status: ${row.status_words}.`
        : 'Nothing was booked, so nothing was added to your itinerary.' })
      return
    }
    setPhase({ p: 'refused', words: 'The call has not finished after 8 minutes; its result is kept on the server and will show in your reservations.' })
  }

  // a typed "yes" binds to THIS card while its read-back is showing
  useEffect(() => {
    if (phase.p !== 'readback') return
    const { callId, sha, lines } = phase
    setPendingYes((said) => { approve(callId, sha, lines, 'chat', said).catch((e) => setPhase({ p: 'refused', words: (e as Error).message })) })
    return () => setPendingYes(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- re-armed for each new read-back card
  }, [phase.p === 'readback' ? phase.callId : null])

  const run = (f: () => Promise<void>) => () => { f().catch((e) => setPhase({ p: 'refused', words: (e as Error).message })) }
  // the ONE essential still missing, asked as a question (null: nothing — she prepares it herself)
  const missing: null | { key: 'date' | 'time' | 'count' | 'name'; ask: string } =
    !d.ask && !d.date ? { key: 'date', ask: 'Which day?' } : !d.ask && !d.time ? { key: 'time', ask: 'What time?' }
      : !(d.count >= 1) ? { key: 'count', ask: 'For how many?' } : d.name.trim().length < 2 ? { key: 'name', ask: 'Whose name should it be under?' } : null
  useEffect(() => {
    // once the saved details are known, she prepares it herself — nothing to press
    if (autoTried || phase.p !== 'details' || saved === null || missing || d.venueLang.trim().length < 2) return
    setAutoTried(true)
    prepare().catch((e) => setPhase({ p: 'refused', words: (e as Error).message }))
  // eslint-disable-next-line react-hooks/exhaustive-deps -- re-checked as the details arrive
  }, [saved, missing?.key, d.venueLang, phase.p, autoTried])
  const surname = d.name.trim().split(/\s+/).pop() ?? ''
  const dayWords = d.date ? new Date(`${d.date}T12:00:00Z`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' }) : ''
  const confirmSentence = `Book ${venue} for ${d.count}${d.unit === 'people' ? '' : ` ${d.unit}`}, ${d.ask ? 'whenever they have space' : `${dayWords} at ${d.time}`}, under ${surname}?`
  // Sasha 86 · explicit ink and paper: inside the dark chat an input inherited white text on its white box (invisible)
  const input = { width: '100%', padding: '4px 6px', border: '1px solid rgba(0,0,0,.25)', borderRadius: 6, color: '#111', background: '#fff', colorScheme: 'light' } as const
  const needs = [
    d.activity.trim().length < 2 && 'what to book', d.venueLang.trim().length < 2 && `how to say it there`,
    !d.ask && !d.date && 'a day', !d.ask && !d.time && 'a time', !(d.count >= 1) && 'how many', d.name.trim().length < 2 && 'your name',
    phase.p === 'preparing' && 'the read-back',
  ]
  return (
    <div ref={stepRef} style={{ marginTop: 10, borderTop: '1px solid rgba(0,0,0,.1)', paddingTop: 10 }}>
      {phase.p === 'preparing' && !showForm && <div style={{ fontSize: 13 }}>Getting it ready for {venue}…</div>}
      {phase.p === 'details' && missing && !showForm && (
        // Sasha 96 · ONE question, only for something essential the request didn't say
        <div style={{ fontSize: 13 }}>
          <div style={{ marginBottom: 4 }}>{missing.ask}</div>
          {missing.key === 'date' && <input style={{ ...input, width: 180 }} type="date" value={d.date} onChange={(e) => setD({ ...d, date: e.target.value })} />}
          {missing.key === 'time' && <input style={{ ...input, width: 140 }} type="time" value={d.time} onChange={(e) => setD({ ...d, time: e.target.value })} />}
          {missing.key === 'count' && <input style={{ ...input, width: 100 }} type="number" min={1} max={100} value={d.count || ''} onChange={(e) => setD({ ...d, count: Number(e.target.value) })} />}
          {missing.key === 'name' && <input style={{ ...input, width: 240 }} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} />}
        </div>
      )}
      {(showForm || (phase.p === 'refused' && showForm)) && (phase.p === 'details' || phase.p === 'preparing' || phase.p === 'refused') && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 13 }}>
          <label>What (your words)<input style={input} value={d.activity} onChange={(e) => setD({ ...d, activity: e.target.value })} /></label>
          <label>As Sasha will say it there<input style={input} value={d.venueLang} onChange={(e) => { setLangEdited(true); setD({ ...d, venueLang: e.target.value }) }} /></label>
          <label style={{ gridColumn: '1 / -1' }}><input type="checkbox" checked={d.ask} onChange={(e) => setD({ ...d, ask: e.target.checked })} /> No set time — ask them when they have space</label>
          {!d.ask && <label>Day<input style={input} type="date" value={d.date} onChange={(e) => setD({ ...d, date: e.target.value })} /></label>}
          {!d.ask && <label>Time<input style={input} type="time" value={d.time} onChange={(e) => setD({ ...d, time: e.target.value })} /></label>}
          <label>How many<input style={input} type="number" min={1} max={100} value={d.count} onChange={(e) => setD({ ...d, count: Number(e.target.value) })} /></label>
          <label>Counted in<select style={input} value={d.unit} onChange={(e) => setD({ ...d, unit: e.target.value })}>
            <option value="people">people</option><option value="sessions">sessions</option><option value="pieces">pieces</option><option value="places">places</option></select></label>
          {!d.ask && <label>Length in minutes (if it matters)<input style={input} inputMode="numeric" value={d.duration} onChange={(e) => setD({ ...d, duration: e.target.value })} /></label>}
          <label>Your name<input style={input} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></label>
          <label style={{ gridColumn: '1 / -1' }}>Your mobile, given only if they ask (+34…)<input style={input} value={d.mobile} onChange={(e) => setD({ ...d, mobile: e.target.value })} /></label>
          {saved && 'consent' in saved && (
            <div style={{ gridColumn: '1 / -1', fontSize: 12 }}>
              {saved.contact
                ? <>Using your saved name and mobile. <button type="button" onClick={run(forget)} style={{ textDecoration: 'underline' }}>Delete my saved details</button></>
                : <label><input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} /> Save my name and mobile for next time.{' '}
                    {saved.consent.text} <a href={saved.consent.privacy} target="_blank" rel="noopener noreferrer">Privacy</a></label>}
            </div>
          )}
          {saved && 'why' in saved && <div style={{ gridColumn: '1 / -1', fontSize: 12, opacity: 0.7 }}>Saved details aren&rsquo;t available: {saved.why}</div>}
          {note && <div style={{ gridColumn: '1 / -1', fontSize: 12 }}>{note}</div>}
          <div style={{ gridColumn: '1 / -1' }}>
            <GatedButton label="Use these details" onClick={run(async () => { setShowForm(false); await prepare() })} needs={needs} />
          </div>
        </div>
      )}
      {phase.p === 'refused' && <div style={{ marginTop: 6 }}>{phase.words}
        {!showForm && <> <button type="button" onClick={() => { setShowForm(true); setPhase({ p: 'details' }) }} style={{ fontSize: 12, textDecoration: 'underline' }}>Change details</button></>}</div>}
      {(phase.p === 'readback' || phase.p === 'placing') && (
        <div>
          {/* Sasha 96 · ONE confirmation sentence; the yes still binds to the full read-back's hash, which is one tap away */}
          <div style={{ fontWeight: 600 }}>{confirmSentence}</div>
          {phase.p === 'readback' && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
              <GatedButton label="Yes" onClick={run(() => approve(phase.callId, phase.sha, phase.lines, 'button', null))} needs={[]} />
              <GatedButton label="No" onClick={() => { setPendingYes(null); setPhase({ p: 'not_now' }) }} needs={[]} />
              <span style={{ fontSize: 12, opacity: 0.7 }}>or say “yes”</span>
              <button type="button" onClick={() => { setPendingYes(null); setShowForm(true); setPhase({ p: 'details' }) }} style={{ fontSize: 12, textDecoration: 'underline' }}>Change details</button>
            </div>
          )}
          <details style={{ marginTop: 6, fontSize: 13 }}>
            <summary>See exactly what I&rsquo;ll say</summary>
            <div style={{ fontSize: 12, opacity: 0.75, margin: '4px 0' }}>Your yes covers exactly these words:</div>
            <ol style={{ paddingLeft: 18 }}>{phase.lines.map((l, i) => <li key={i}>{l}</li>)}</ol>
          </details>
          {phase.p === 'placing' && <div>Placing the call…</div>}
        </div>
      )}
      {phase.p === 'not_now' && <div>Nothing was dialled. Say the word if you want me to try again.</div>}
      {phase.p === 'calling' && <div>{phase.say}</div>}
      {phase.p === 'result' && (
        <div>
          <div style={{ fontWeight: 600 }}>{phase.view.say}</div>
          {phase.view.venue_words ? <div style={{ marginTop: 4 }}>What they said, word for word: &ldquo;{phase.view.venue_words}&rdquo;</div> : null}
          {phase.view.read_by ? <div style={{ fontSize: 12, opacity: 0.7 }}>The outcome is {phase.view.read_by}; their words are verbatim.</div> : null}
          <div style={{ marginTop: 6 }}>{phase.itinerary}</div>
          {phase.receipt ? <ReceiptCard path={phase.receipt} /> : null}
        </div>
      )}
    </div>
  )
}
