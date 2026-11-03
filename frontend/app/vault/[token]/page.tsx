'use client'
/**
 * Sasha 333 · THE TRAVELLER VAULT — a group member's OWN page (no sign-in: the signed, single-person, 7-day link is the key).
 * Passport (number, country, expiry, name as on the passport, date of birth — what the airline needs), frequent-flyer and hotel
 * loyalty numbers. Saved straight into THEIR Keep (encrypted; never logged; never sent to the AI model). What comes back is a mask only;
 * the organiser sees ✓ / missing. Delete everything from here at any time.
 */
import { use, useCallback, useEffect, useState } from 'react'
import { apiUrl } from '@/lib/api'

type Page = { name: string; company?: string; destination?: string; saved: { type: string; masked: string; item_id: string }[] }
const empty = { number: '', country: '', expires_on: '', name: '', born_on: '' }

export default function VaultPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params)
  const url = apiUrl(`/api/booking/vault/${encodeURIComponent(token)}`)
  const [p, setP] = useState<Page | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [pp, setPp] = useState(empty)
  const [loy, setLoy] = useState([{ program: '', number: '' }])
  const [busy, setBusy] = useState(false)
  const [said, setSaid] = useState<string | null>(null)

  const load = useCallback(async () => {
    const r = await fetch(url, { cache: 'no-store' }).catch(() => null)
    const j = r ? await r.json().catch(() => null) : null
    if (r?.ok && j) { setP(j as Page); setErr(null) } else setErr((j && (j.message as string)) || 'This page couldn’t be opened.')
  }, [url])
  useEffect(() => { load() }, [load])

  const save = async () => {
    setBusy(true); setSaid(null)
    const body = { passport: pp.number ? pp : null, loyalty: loy.filter(l => l.number.trim()) }
    const r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }).catch(() => null)
    const j = r ? await r.json().catch(() => null) : null
    setBusy(false)
    if (r?.ok) { setPp(empty); setLoy([{ program: '', number: '' }]); setSaid('Saved.'); load() }   // the values leave the page's memory
    else setSaid((j && (j.message as string)) || 'That wasn’t saved — try again.')
  }
  const erase = async (item?: string) => {
    setBusy(true)
    await fetch(url + (item ? `?item=${encodeURIComponent(item)}` : ''), { method: 'DELETE' }).catch(() => null)
    setBusy(false); setSaid(item ? 'Deleted.' : 'Everything deleted.'); load()
  }

  const field = (k: keyof typeof empty, label: string, type = 'text', ph = '') => (
    <label style={{ display: 'block', margin: '8px 0' }}>{label}
      <input type={type} autoComplete="off" value={pp[k]} placeholder={ph} onChange={e => setPp({ ...pp, [k]: e.target.value })}
        style={{ display: 'block', width: '100%', padding: 8, boxSizing: 'border-box' }} /></label>)

  if (err) return <main style={{ maxWidth: 520, margin: '40px auto', padding: '0 16px', fontFamily: 'system-ui' }}><p>{err}</p></main>
  if (!p) return <main style={{ maxWidth: 520, margin: '40px auto', padding: '0 16px', fontFamily: 'system-ui' }}><p>Loading…</p></main>
  return (
    <main style={{ maxWidth: 520, margin: '24px auto', padding: '0 16px', fontFamily: 'system-ui, sans-serif' }}>
      <h1 style={{ fontSize: 22 }}>Hi {p.name.split(' ')[0]} — your travel details</h1>
      <p style={{ color: '#475467' }}>{p.company} is booking your trip to {p.destination}. Your numbers are encrypted and only used to book
        your travel; the organiser sees only that they’re there, never the numbers.</p>
      {p.saved.length > 0 && <section data-saved>
        <h2 style={{ fontSize: 16 }}>Saved</h2>
        {p.saved.map(s => <div key={s.item_id} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
          <span>✓ {s.masked}</span><button type="button" disabled={busy} onClick={() => erase(s.item_id)}>Delete</button></div>)}
        <button type="button" disabled={busy} onClick={() => erase()} style={{ marginTop: 8 }}>Delete everything</button>
      </section>}
      <section>
        <h2 style={{ fontSize: 16 }}>Passport</h2>
        {field('name', 'Name exactly as on the passport')}
        {field('number', 'Passport number')}
        {field('country', 'Issuing country (2 letters, e.g. ES)', 'text', 'ES')}
        {field('expires_on', 'Expiry date', 'date')}
        {field('born_on', 'Date of birth', 'date')}
        <h2 style={{ fontSize: 16 }}>Frequent-flyer and hotel loyalty</h2>
        {loy.map((l, i) => <div key={i} style={{ display: 'flex', gap: 8 }}>
          <input placeholder="Programme (e.g. Iberia Plus, Marriott Bonvoy)" value={l.program} autoComplete="off"
            onChange={e => setLoy(loy.map((x, j) => j === i ? { ...x, program: e.target.value } : x))} style={{ flex: 1, padding: 8 }} />
          <input placeholder="Number" value={l.number} autoComplete="off"
            onChange={e => setLoy(loy.map((x, j) => j === i ? { ...x, number: e.target.value } : x))} style={{ flex: 1, padding: 8 }} /></div>)}
        <button type="button" onClick={() => setLoy([...loy, { program: '', number: '' }])} style={{ marginTop: 6 }}>Add another</button>
        <div><button type="button" disabled={busy} onClick={save} style={{ marginTop: 14, padding: '10px 18px' }}>Save</button></div>
        {said && <p data-said>{said}</p>}
      </section>
    </main>)
}
