'use client'
/**
 * Sasha 351 · PEOPLE — the company's ONE standing roster. Each worker once: name, grade, home AIRPORT (editable), contact, and their
 * documents in their OWN vault (their passport saved once, for every trip). A trip is a SELECTION from it: tick who travels, and they
 * are put on it (a link each — nothing copied) and planned from their home airport. Every press answers (lib/outcome, Sasha 346–348).
 */
import { useEffect, useState } from 'react'
import { bookingReq } from '@/lib/booking-client'
import { heard as heardWords, observe, stillGoing, toConsole } from '@/lib/outcome'
import { T, card as cardS, field, btn, btn2, small } from '@/lib/group-theme'

type Person = { id: string; name: string; grade?: string | null; home_airport?: string | null; home_city?: string | null
  email?: string | null; phone?: string | null; vault?: { passport: boolean } }
type Res = Awaited<ReturnType<typeof bookingReq>>
const BLANK = { name: '', grade: '', home_airport: '', home_city: '', email: '', phone: '' }
const FIELDS: [keyof typeof BLANK, string, number][] = [['name', 'Name', 170], ['grade', 'Grade', 90], ['home_airport', 'Home airport (MAD)', 130],
  ['home_city', 'Home city', 120], ['email', 'Email', 190], ['phone', 'Phone (+34…)', 130]]

export default function People({ onTrip, trip }: { onTrip: string[]; trip: string | null }) {
  const [ps, setPs] = useState<Person[] | null>(null)
  const [company, setCompany] = useState<string | null>(null)
  const [said, setSaid] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [ticked, setTicked] = useState<string[]>([])
  const [draft, setDraft] = useState({ ...BLANK })
  const [edit, setEdit] = useState<string | null>(null)
  const [ed, setEd] = useState<Record<string, string>>({})
  const [docs, setDocs] = useState<{ id: string; link: string } | null>(null)

  const pull = async () => {
    const r = await bookingReq('/api/booking/group/people')
    if (!r.ok) throw new Error(String(r.json.message || r.json.rule || r.status))
    setPs((r.json.people as Person[]) || [])
    setCompany(((r.json.company || null) as { name?: string } | null)?.name || null)
  }
  useEffect(() => {
    observe(pull(), 'Reading the roster', toConsole)
    const t = setInterval(() => observe(pull(), 'Reading the roster', toConsole), 10000)
    return () => clearInterval(t)
  }, [])

  // every press answers: the server's words (heard), else what happened; a press while another runs is told so
  const run = (name: string, fn: () => Promise<Res>, then?: (r: Res) => void) => () => {
    if (busy) { setSaid(stillGoing(busy, name)); return }
    setBusy(name); setSaid(`${name}…`)
    observe(fn().then(r => { setSaid(heardWords(name, r)); if (r.ok) then?.(r); return pull() }).finally(() => setBusy(null)), name, setSaid)
  }
  const add = run('Add to the roster', () => bookingReq('/api/booking/group/people', { rows: [Object.fromEntries(Object.entries(draft).filter(([, v]) => v.trim()))] }),
    r => { if (r.json.done) setDraft({ ...BLANK }) })
  const save = (id: string) => run('Save', () => bookingReq(`/api/booking/group/people/${id}`, ed), r => { if (r.json.done) setEdit(null) })
  const documents = (id: string) => run('Documents', () => bookingReq(`/api/booking/group/people/${id}/documents`, {}),
    r => { if (typeof r.json.link === 'string') setDocs({ id, link: r.json.link }) })
  const choose = run('Choose travellers', () => bookingReq('/api/booking/group/choose', { who: ticked }), r => { if (r.json.done) setTicked([]) })

  return (
    <section data-people style={{ ...cardS, marginBottom: 16 }}>
      <h2 style={{ fontSize: 17, margin: '0 0 4px' }}>People{company ? ` · ${company}` : ''}</h2>
      <p style={{ margin: '0 0 10px', color: T.muted, fontSize: 13.5 }}>Each person once — their details and passport serve every trip. Tick who travels.</p>
      <div data-person-add style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
        {FIELDS.map(([k, label, w]) => (
          <input key={k} aria-label={label} placeholder={label} value={draft[k]} onChange={e => setDraft({ ...draft, [k]: e.target.value })}
            style={{ ...field, width: w }} />))}
        <button type="button" onClick={add} style={btn2}>Add to the roster</button>
      </div>
      {said && <p data-people-said role="status" aria-live="polite" style={{ whiteSpace: 'pre-line', margin: '6px 0' }}>{said}</p>}
      {docs && <p data-docs-link style={{ margin: '6px 0' }}><a href={docs.link} target="_blank" rel="noopener" style={{ color: T.link, textDecoration: 'underline' }}>Open their vault page</a>
        <span style={{ color: T.muted }}> — or forward it to them</span></p>}
      {ps === null ? <p>Reading the roster…</p> : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead><tr>{['On this trip', 'Name', 'Grade', 'Home airport', 'Home city', 'Contact', 'Passport', ''].map(h =>
              <th key={h} style={{ textAlign: 'left', borderBottom: `1px solid ${T.border}`, padding: '6px 8px', color: T.muted }}>{h}</th>)}</tr></thead>
            <tbody>{ps.map(p => edit === p.id ? (
              <tr key={p.id} data-person={p.id} style={{ borderBottom: `1px solid ${T.second}` }}>
                <td />
                {(['name', 'grade', 'home_airport', 'home_city'] as const).map(k => (
                  <td key={k} style={{ padding: '4px' }}><input aria-label={k} value={ed[k] ?? (p[k] || '')} onChange={e => setEd({ ...ed, [k]: e.target.value })} style={{ ...field, width: 120 }} /></td>))}
                <td style={{ padding: '4px' }}><input aria-label="email" value={ed.email ?? (p.email || '')} onChange={e => setEd({ ...ed, email: e.target.value })} style={{ ...field, width: 170 }} /></td>
                <td />
                <td><button type="button" onClick={save(p.id)} style={small}>Save</button></td>
              </tr>) : (
              <tr key={p.id} data-person={p.id} style={{ borderBottom: `1px solid ${T.second}` }}>
                <td style={{ padding: '6px 8px' }}>{onTrip.includes(p.id) ? <span style={{ color: T.booked }}>✓ on it</span>
                  : <input type="checkbox" aria-label={`Choose ${p.name}`} data-tick={p.id} checked={ticked.includes(p.id)}
                      onChange={e => setTicked(t => (e.target.checked ? [...t, p.id] : t.filter(x => x !== p.id)))} />}</td>
                <td style={{ padding: '6px 8px' }}>{p.name}</td>
                <td style={{ padding: '6px 8px' }}>{p.grade || '—'}</td>
                <td style={{ padding: '6px 8px' }}>{p.home_airport || '—'}</td>
                <td style={{ padding: '6px 8px' }}>{p.home_city || '—'}</td>
                <td style={{ padding: '6px 8px', color: T.muted }}>{[p.email, p.phone].filter(Boolean).join(' · ') || '—'}</td>
                <td style={{ padding: '6px 8px' }} data-passport={p.vault?.passport ? '1' : '0'}>{p.vault?.passport ? 'Passport ✓' : 'missing'}</td>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                  <button type="button" onClick={() => { setEdit(p.id); setEd({}) }} style={small}>Edit</button>{' '}
                  <button type="button" data-documents={p.id} onClick={documents(p.id)} style={small}>Documents</button></td>
              </tr>))}</tbody>
          </table>
        </div>)}
      <div style={{ marginTop: 10 }}>
        <button type="button" data-choose-ticked onClick={choose} style={btn}>
          {ticked.length ? `Put the ${ticked.length} ticked on ${trip || 'this trip'}` : `Put the ticked on ${trip || 'this trip'}`}</button>
      </div>
    </section>)
}
