'use client'

/**
 * Sasha 95 · THE SLOT LINK IN THE CHAT — for a venue whose only booking route is a platform widget (CoverManager,
 * TheFork…). Sasha never presses the platform's button: she prepares the venue's own page on its platform (read from
 * the venue's site), says plainly that the guest makes the final press, records that they opened it and that they
 * booked, and watches for the confirmation they forward. Every sentence is the server's (backend slot_link.read_back).
 */
import { useState } from 'react'
import { bookingReq, refusal } from '@/lib/booking-client'
import { GatedButton } from '../booking-helper/GatedButton'

type Link = { link_id: string; url: string; sha256: string; platform: string; lines: string[] }
type Draft = { parts?: { when?: { mode: string; at?: string }; how_many?: { count: number; unit: string }; who?: { name: string } } } | null

export default function ChatBookingLink({ readId, platform, draft, openAt }: {
  readId: string; platform: string; draft: Draft; openAt?: string | null }) {
  const parts = draft?.parts ?? {}
  const at = parts.when?.mode === 'at' && parts.when.at ? parts.when.at.split('T')
    : openAt && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(openAt) ? openAt.split('T') : ['', '']
  const [d, setD] = useState({ date: at[0], time: at[1], party: parts.how_many?.count ?? 2, name: parts.who?.name ?? '' })
  const [link, setLink] = useState<Link | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const input = { width: '100%', padding: '4px 6px', border: '1px solid rgba(0,0,0,.25)', borderRadius: 6, color: '#111', background: '#fff', colorScheme: 'light' } as const

  async function prepare() {
    setNote(null)
    const r = await bookingReq('/api/booking/links', { read_id: readId, date: d.date, time: d.time, party: d.party, name: d.name.trim() })
    if (!r.ok) { setNote(`No link — ${refusal(r.json, r.status)}`); return }
    const rb = r.json.read_back as { lines: string[]; sha256: string }
    setLink({ link_id: String(r.json.link_id), url: String(r.json.url), sha256: rb.sha256, platform: String(r.json.platform), lines: rb.lines })
    setStatus('offered')
  }
  async function state(path: string, body?: unknown) {
    if (!link) return
    const g = await bookingReq(`/api/booking/links/${link.link_id}${path}`, body)
    if (!g.ok) { setNote(`Not recorded — ${refusal(g.json, g.status)}`); return }
    setStatus(String(g.json.status ?? '')); setNote(typeof g.json.say === 'string' ? g.json.say : null)
  }
  const run = (f: () => Promise<void>) => () => { f().catch((e) => setNote(`Stopped: ${(e as Error).message}`)) }

  return (
    <div style={{ marginTop: 10, borderTop: '1px solid rgba(0,0,0,.1)', paddingTop: 10, fontSize: 13 }}>
      <div style={{ marginBottom: 6 }}>They book only through {platform}: I&rsquo;ll get their page ready with what to pick — <strong>you make the final press</strong>.</div>
      {!link && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          <label>Day<input style={input} type="date" value={d.date} onChange={(e) => setD({ ...d, date: e.target.value })} /></label>
          <label>Time<input style={input} type="time" value={d.time} onChange={(e) => setD({ ...d, time: e.target.value })} /></label>
          <label>How many<input style={input} type="number" min={1} max={20} value={d.party} onChange={(e) => setD({ ...d, party: Number(e.target.value) })} /></label>
          <label>Your name<input style={input} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></label>
          <div style={{ gridColumn: '1 / -1' }}>
            <GatedButton label={`Get their ${platform} page ready`} onClick={run(prepare)}
              needs={[!d.date && 'a day', !d.time && 'a time', !(d.party >= 1) && 'how many', d.name.trim().length < 2 && 'your name']} />
          </div>
        </div>
      )}
      {link && (
        <div>
          {link.lines.map((l, i) => <div key={i} style={{ marginBottom: 2 }}>{l}</div>)}
          <a href={link.url} target="_blank" rel="noopener noreferrer"
            style={{ display: 'inline-block', marginTop: 6, padding: '4px 10px', border: '1px solid rgba(0,0,0,.3)', borderRadius: 6 }}
            onClick={() => { state('/opened', { read_back_sha256: link.sha256 }).catch(() => { /* shown by the next state */ }) }}>
            Open their {link.platform} page ↗
          </a>
          <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
            <GatedButton label="I booked it" onClick={run(() => state('/booked', { how: 'button' }))}
              needs={[status === 'offered' && 'their page to be opened first']} done={(status === 'guest_booked' || status === 'confirmed') && 'Noted'} />
            <GatedButton label="Check for the confirmation" onClick={run(() => state(''))} needs={[]} />
          </div>
        </div>
      )}
      {note && <div style={{ marginTop: 6 }}>{note}</div>}
    </div>
  )
}
