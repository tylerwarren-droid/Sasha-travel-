'use client'
/**
 * Sasha 241 · THE SHARED CARDS (EU 232 §2.0 item 3): moved here from S2App.tsx unchanged — /s2 renders them as before, and /next's
 * SashaChat now draws the same ones (keep_capture, capabilities, plans, notice, counter_card, my_cards, accident, claim_status,
 * wa_open, activities) through SharedCard. One look, one place.
 */
import { PlaceCard } from './PlaceCard'   // Sasha 252 · activities are places
import { useRef, useState } from 'react'
import { untag } from '@/lib/no-test-label.mjs'
import { subsHeading, subsFooter } from '@/lib/subscriptions-heading.mjs'   // Sasha 246

type Ev = Record<string, any>   // eslint-disable-line @typescript-eslint/no-explicit-any
export const C = { bg: '#0b0b10', card: '#16151d', line: 'rgba(255,255,255,.1)', gold: '#E8B923', dim: 'rgba(255,255,255,.6)' }
export type Plan = { kind: 'dinner' | 'spa' | 'venue' | 'flight' | 'hotel' | 'car'; title: string; when: string; where?: string; status: string; reference?: string; id?: string }

export function Box({ k, h, children, tone }: { k: string; h?: string; children?: React.ReactNode; tone?: string }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${tone || C.line}`, borderRadius: 16, padding: 14, marginTop: 8 }}>
      <div style={{ fontSize: 11.5, letterSpacing: '.12em', textTransform: 'uppercase', color: C.dim }}>{k}</div>
      {h ? <div style={{ fontWeight: 700, marginTop: 4 }}>{h}</div> : null}
      {children ? <div style={{ marginTop: 8 }}>{children}</div> : null}
    </div>
  )
}

/** Sasha 224 · the Keep from a photo: the photo is shrunk on the phone, read once by the backend and dropped; back comes a MASKED
 *  card to confirm — nothing is saved until Confirm, and the number never reaches the chat. */
export async function shrink(file: File): Promise<string> {
  const bmp = await createImageBitmap(file)
  const scale = Math.min(1, 1800 / Math.max(bmp.width, bmp.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bmp.width * scale); canvas.height = Math.round(bmp.height * scale)
  canvas.getContext('2d')?.drawImage(bmp, 0, 0, canvas.width, canvas.height)
  bmp.close?.()
  return canvas.toDataURL('image/jpeg', 0.88).split(',')[1] ?? ''
}

/** Sasha 228 · `base` lets the phone handoff (/s2?handoff=…, not signed in) use its one-time code's routes; `onSaved` tells it. */
export function KeepCapture({ what, base = '/api/s2-keep/scan', onSaved }: { what: 'passport' | 'loyalty'; base?: string; onSaved?: (item: string) => void }) {
  type Phase = { p: 'pick' } | { p: 'reading' } | { p: 'confirm'; token: string; shown: string[] } | { p: 'saving' } | { p: 'saved'; item: string } | { p: 'error'; why: string }
  const [ph, setPh] = useState<Phase>({ p: 'pick' })
  const input = useRef<HTMLInputElement | null>(null)
  const label = what === 'passport' ? "your passport's photo page" : 'your card, or its Apple Wallet screenshot'
  async function picked(f?: File | null) {
    if (!f) return
    setPh({ p: 'reading' })
    try {
      const image = await shrink(f)
      const r = await fetch(base, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ kind: what, image, media_type: 'image/jpeg' }) })
      const j = await r.json().catch(() => ({}))
      setPh(j?.ok ? { p: 'confirm', token: j.token, shown: j.shown || [j.masked] } : { p: 'error', why: j?.message || 'That photo couldn\u2019t be read.' })
    } catch { setPh({ p: 'error', why: 'That photo couldn\u2019t be read.' }) }
    if (input.current) input.current.value = ''
  }
  async function act(token: string, action: 'confirm' | 'discard') {
    if (action === 'discard') { fetch(`${base}/${encodeURIComponent(token)}/discard`, { method: 'POST' }).catch(() => {}); setPh({ p: 'pick' }); return }
    setPh({ p: 'saving' })
    const r = await fetch(`${base}/${encodeURIComponent(token)}/confirm`, { method: 'POST' }).catch(() => null)
    const j = r ? await r.json().catch(() => ({})) : {}
    setPh(j?.ok ? { p: 'saved', item: j.item } : { p: 'error', why: j?.message || 'It wasn\u2019t saved — try again.' })
    if (j?.ok) onSaved?.(String(j.item || ''))
  }
  const btn = { padding: '9px 16px', borderRadius: 999, border: `1px solid ${C.gold}`, background: 'transparent', color: C.gold, fontWeight: 700 } as const
  return (
    <Box k={what === 'passport' ? 'Add your passport' : 'Add a loyalty card'} h={ph.p === 'saved' ? `Saved in your Keep: ${untag(ph.item)}` : ph.p === 'confirm' ? 'Is this yours?' : undefined}
      tone={ph.p === 'saved' ? 'rgba(126,226,168,.5)' : undefined}>
      <input ref={input} type="file" accept="image/*" hidden onChange={e => picked(e.target.files?.[0])} aria-label="Photo for your Keep" />
      {ph.p === 'pick' && <><div style={{ fontSize: 14, color: C.dim, margin: '4px 0 10px' }}>A photo of {label}. It&rsquo;s read once and not kept; only a masked number is shown here.</div>
        <button onClick={() => input.current?.click()} style={{ ...btn, background: C.gold, color: '#111' }}>Take or choose a photo</button></>}
      {ph.p === 'reading' && <div style={{ fontSize: 14, color: C.dim }}>Reading it…</div>}
      {ph.p === 'saving' && <div style={{ fontSize: 14, color: C.dim }}>Saving…</div>}
      {ph.p === 'confirm' && <>{ph.shown.map((l, i) => <div key={i} style={{ fontSize: 15, padding: '2px 0' }}>{untag(l)}</div>)}
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button onClick={() => act(ph.token, 'confirm')} style={{ ...btn, background: C.gold, color: '#111' }}>Confirm</button>
          <button onClick={() => act(ph.token, 'discard')} style={btn}>Retake</button></div></>}
      {ph.p === 'saved' && <div style={{ fontSize: 13.5, color: C.dim }}>Encrypted. Sasha only ever sees the mask.</div>}
      {ph.p === 'error' && <><div style={{ fontSize: 14, color: '#f19999', margin: '4px 0 10px' }}>{ph.why}</div>
        <button onClick={() => input.current?.click()} style={btn}>Try another photo</button></>}
    </Box>
  )
}

/** Sasha 230 · the drafted WhatsApp, pre-filled in the person's OWN WhatsApp: they press send (Sasha sends nothing). */
export function WaOpen({ c }: { c: { to: { name?: string | null; number?: string }; text: string; open: string; why: string } }) {
  const who = untag(c.to.name || c.to.number || 'them')
  return (
    <Box k="Ready in your WhatsApp" h={`To ${who}${c.to.name && c.to.number ? ` · ${c.to.number}` : ''}`}>
      <div style={{ fontSize: 15, lineHeight: 1.45, whiteSpace: 'pre-wrap', padding: '8px 10px', borderRadius: 12, background: 'rgba(37,211,102,.08)', border: '1px solid rgba(37,211,102,.25)' }}>{untag(c.text)}</div>
      <a href={c.open} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 10, padding: '10px 16px', borderRadius: 999, background: '#25D366', color: '#062b14', fontWeight: 700, textDecoration: 'none' }}>Open in WhatsApp</a>
      <div style={{ fontSize: 12.5, color: C.dim, marginTop: 8 }}>You press send — Sasha hasn&rsquo;t sent anything.</div>
    </Box>
  )
}

/** Sasha 226 · a plan's date, en-GB and absolute ("Sat 24 Oct · 21:00"; a date alone has no clock) — never "in 2 days". */
function fmtWhen(iso: string): string {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso)
  const d = dateOnly ? new Date(`${iso}T00:00`) : new Date(iso)   // a bare date is the person's own day, not UTC midnight
  if (isNaN(d.getTime())) return untag(iso)
  const day = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  return dateOnly ? day : `${day} · ${d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false })}`
}
const PLAN_ICON: Record<string, string> = { dinner: '🍽️', venue: '🍽️', spa: '💆', flight: '✈️', hotel: '🏨', car: '🚗' }

export function Plans({ items, on }: { items: Plan[]; on?: string }) {
  return (
    <Box k={on ? `Your plans on ${/^\d{4}-\d{2}-\d{2}/.test(on) ? fmtWhen(on.slice(0, 10)) : untag(on)}` : 'Your plans'}>
      {items.length === 0 ? <div style={{ fontSize: 14.5, color: C.dim }}>Nothing coming up.</div> : items.map((p, i) => (
        <div key={p.id || `${p.when}-${i}`} style={{ display: 'flex', gap: 10, padding: '8px 0', borderTop: i ? `1px solid ${C.line}` : 'none' }}>
          <span style={{ fontSize: 20, lineHeight: 1.2 }} aria-hidden>{PLAN_ICON[p.kind] || '📌'}</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 700 }}>{untag(p.title)}</div>
            <div style={{ fontSize: 13.5, color: 'rgba(255,255,255,.88)' }}>{fmtWhen(p.when)}{p.where ? ` · ${untag(p.where)}` : ''}</div>
            <div style={{ fontSize: 12.5, color: C.dim }}>{untag(p.status)}{p.reference ? ` · Ref ${untag(p.reference)}` : ''}</div>
          </div>
        </div>))}
    </Box>
  )
}

/** CR 75 · fine print — every line rests on a quote; "source" opens the sentence, its page and the date it was read. */
type Q = { quote: string; source_url: string; read_at?: string }
export function Sources({ quotes }: { quotes?: Q[] }) {
  const [open, setOpen] = useState(false)
  if (!quotes || !quotes.length) return null
  return (
    <span>
      <button onClick={() => setOpen(o => !o)} style={{ background: 'none', border: 0, color: C.gold, fontSize: 12, padding: '0 0 0 6px', textDecoration: 'underline' }}>
        {open ? 'hide' : 'source'}</button>
      {open && quotes.map((q, i) => (
        <div key={i} style={{ fontSize: 12.5, color: C.dim, borderLeft: `2px solid ${C.line}`, margin: '6px 0', padding: '2px 8px' }}>
          &ldquo;{q.quote}&rdquo;<br /><a href={q.source_url} target="_blank" rel="noreferrer" style={{ color: C.dim }}>{(() => { try { return new URL(q.source_url).hostname } catch { return 'source' } })()}</a>
          {q.read_at ? ` · read ${q.read_at}` : ''}</div>))}
    </span>)
}
type Line = { say: string; quotes?: Q[] }
export function Lines({ title, lines, tone }: { title: string; lines?: Line[]; tone?: string }) {
  if (!lines || !lines.length) return null
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 11.5, letterSpacing: '.1em', textTransform: 'uppercase', color: tone || C.dim }}>{title}</div>
      {lines.map((l, i) => <div key={i} style={{ fontSize: 14.5, padding: '3px 0' }}>{untag(l.say)}<Sources quotes={l.quotes} /></div>)}
    </div>)
}
export function CounterCard({ card }: { card: Ev }) {
  const k = card.counter || {}
  return (
    <Box k="At the counter" h={card.card ? `Pay with your ${untag(card.card)}` : 'Your counter card'} tone={C.gold}>
      <Lines title="Decline" lines={k.decline} tone="#f19999" />
      <Lines title="Check first" lines={k.check} tone={C.gold} />
      <Lines title="Keep" lines={k.keep} tone="#7ee2a8" />
      <Lines title="Optional" lines={k.optional} />
      <Lines title="Conditions" lines={card.conditions} />
      <Lines title="Bring" lines={card.bring} />
      <Lines title="If something happens" lines={card.report} />
      <div style={{ fontSize: 12, color: C.dim, marginTop: 10 }}>{untag(card.framing || '')}</div>
    </Box>)
}
export function MyCards({ cards, choose }: { cards: { product: string; network: string; status: string }[]; choose: (t: string) => void }) {
  if (!cards.length) return <Box k="My cards" h="No cards yet">Add one with a photo or its name — only its product is kept, never a number.</Box>
  return (
    <Box k="My cards">
      {cards.map((c, i) => (
        <div key={i} style={{ padding: '8px 0', borderTop: i ? `1px solid ${C.line}` : 'none' }}>
          <div style={{ fontWeight: 700 }}>{untag(c.product)} <span style={{ color: C.dim, fontWeight: 400 }}>· {c.network}</span></div>
          <div style={{ fontSize: 12.5, color: C.dim }}>{untag(c.status)}</div>
          <button onClick={() => choose(`What does my ${untag(c.product)} cover`)} style={{ marginTop: 6, padding: '6px 12px', borderRadius: 999, border: `1px solid ${C.gold}`, background: 'transparent', color: C.gold, fontWeight: 600 }}>
            What does it cover?</button>
        </div>))}
    </Box>)
}
const STEP_NAMES: Record<string, string> = { safety: 'Safety', duties: 'At the scene', photos: 'Photos', statement: 'The statement', clocks: 'Deadlines', notify: 'Notify', claim: 'The claim' }
export function AccidentCard({ view, send }: { view: Ev; send: (t: string) => void }) {
  // the card's own update (a photo sealed) until the next turn sends a new view — derived, not synced in an effect
  const [local, setLocal] = useState<{ base: Ev; v: Ev } | null>(null)
  const v: Ev = local && local.base === view ? local.v : view
  const setV = (x: Ev) => setLocal({ base: view, v: x })
  const [busy, setBusy] = useState<string | null>(null)
  const pick = useRef<HTMLInputElement | null>(null)
  const shot = useRef<string>('')
  const btn = (primary?: boolean) => ({ padding: '9px 16px', borderRadius: 999, border: `1px solid ${C.gold}`, background: primary ? C.gold : 'transparent', color: primary ? '#111' : C.gold, fontWeight: 700, marginRight: 8, marginTop: 8 }) as const
  async function photo(f?: File | null) {
    if (!f || !shot.current) return
    setBusy(shot.current)
    try {
      const image = await shrink(f)
      const r = await fetch('/api/s2-agent/accident-photo', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ shot: shot.current, media_type: 'image/jpeg', content_base64: image }) })
      const j = await r.json().catch(() => ({}))
      if (j?.ok && j.result) setV(j.result)
    } finally { setBusy(null); if (pick.current) pick.current.value = '' }
  }
  const steps: string[] = v.steps || []
  return (
    <Box k={`Accident · ${STEP_NAMES[v.step] || v.step}`} tone={v.step === 'safety' ? '#f19999' : undefined}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>{steps.map(s => <div key={s} style={{ flex: 1, height: 4, borderRadius: 2, background: steps.indexOf(s) <= steps.indexOf(v.step) ? C.gold : C.line }} />)}</div>
      {v.say ? <div style={{ fontSize: 15.5, fontWeight: 600 }}>{untag(v.say)}</div> : null}
      {v.step === 'safety' && <>
        {v.call && <a href={`tel:${v.call.number}`} style={{ display: 'inline-block', marginTop: 10, padding: '12px 22px', borderRadius: 999, background: '#e5484d', color: '#fff', fontWeight: 800, textDecoration: 'none' }}>Call {v.call.number}</a>}
        {v.call?.source && <Sources quotes={[v.call.source]} />}
        <div>{(v.choices || []).map((c: string) => <button key={c} onClick={() => send(c)} style={btn(c === 'no')}>{c[0].toUpperCase() + c.slice(1)}</button>)}</div></>}
      {v.step === 'duties' && <><Lines title="The official rules" lines={v.lines} /><button onClick={() => send('done')} style={btn(true)}>Done</button></>}
      {v.step === 'photos' && <>
        <input ref={pick} type="file" accept="image/*" capture="environment" hidden onChange={e => photo(e.target.files?.[0])} aria-label="Accident photo" />
        {(v.shots || []).map((s: Ev) => (
          <div key={s.shot} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0', borderTop: `1px solid ${C.line}` }}>
            <span style={{ fontSize: 14, color: s.taken ? '#7ee2a8' : '#fff' }}>{s.taken ? '✓ ' : ''}{s.say}</span>
            <button onClick={() => { shot.current = s.shot; pick.current?.click() }} disabled={!!busy} style={{ ...btn(), marginTop: 0, padding: '5px 12px' }}>{busy === s.shot ? '…' : s.taken ? 'Retake' : 'Take'}</button>
          </div>))}
        <button onClick={() => send('done')} style={btn(true)}>Done with photos</button></>}
      {v.step === 'statement' && <>
        <div style={{ fontSize: 13, color: C.dim, marginTop: 6 }}>{untag(v.form || '')} — the facts:</div>
        {Object.entries(v.facts || {}).filter(([, x]) => x && (typeof x !== 'object' || Object.keys(x as object).length)).map(([k, x]) => (
          <div key={k} style={{ fontSize: 14, padding: '2px 0' }}><span style={{ color: C.dim }}>{k.replace(/_/g, ' ')}:</span> {Array.isArray(x) ? x.join(', ') : typeof x === 'object' ? Object.values(x as object).join(' · ') : String(x)}</div>))}
        <div style={{ fontSize: 13.5, color: C.gold, marginTop: 8 }}>Yours to fill with the other driver: {(v.left_for_you || []).join(', ')}.</div>
        {(v.advice || []).map((a: Line, i: number) => <div key={i} style={{ fontSize: 13 }}>{a.say}<Sources quotes={a.quotes} /></div>)}
        <button onClick={() => send('done')} style={btn(true)}>Done</button></>}
      {(v.step === 'clocks' || v.step === 'notify') && (v.clocks || []).map((c: Ev, i: number) => (
        <div key={i} style={{ padding: '6px 0', borderTop: `1px solid ${C.line}` }}>
          <div style={{ fontSize: 14.5 }}>{untag(c.say)}{c.due ? <b style={{ color: C.gold }}> · by {c.due}</b> : null}<Sources quotes={c.quotes} /></div></div>))}
      {v.step === 'clocks' && <button onClick={() => send('done')} style={btn(true)}>Done</button>}
      {v.step === 'notify' && <button onClick={() => send('Notify the rental company')} style={btn(true)}>Notify the rental company</button>}
      {v.step === 'claim' && v.claim_case_id && <button onClick={() => send('File my card claim')} style={btn(true)}>File the card claim</button>}
      {v.handoff && <div style={{ marginTop: 10, padding: 10, borderRadius: 10, border: '1px solid #f19999', color: '#f19999', fontSize: 14 }}>{v.handoff}</div>}
    </Box>)
}
export function ClaimStatus({ claim }: { claim: Ev }) {
  const missing = (claim.evidence || []).filter((e: Ev) => e.missing)
  return (
    <Box k={`Claim · ${claim.state === 'filed' ? 'filed' : claim.state === 'ready_for_portal' ? 'ready for their portal' : 'being prepared'}`} h={untag(claim.card || '')}
      tone={claim.state === 'filed' ? 'rgba(126,226,168,.5)' : undefined}>
      {(claim.deadlines || []).map((d: Ev, i: number) => <div key={i} style={{ fontSize: 14 }}>{untag(d.say)}{d.quote ? <Sources quotes={[d as Q]} /> : null}</div>)}
      {missing.length ? <div style={{ marginTop: 8, fontSize: 13.5 }}><span style={{ color: C.gold }}>Still needed:</span>
        {missing.map((e: Ev) => <div key={e.item} style={{ color: C.dim }}>· {e.item.replace(/_/g, ' ')} — {e.where}</div>)}</div> : null}
      {(claim.replies || []).map((r: Ev) => <div key={r.reply_id} style={{ marginTop: 8, fontSize: 13.5, borderLeft: `2px solid ${C.line}`, paddingLeft: 8 }}>
        <span style={{ color: C.dim }}>They wrote:</span> &ldquo;{r.text?.text}&rdquo;</div>)}
      {claim.note ? <div style={{ fontSize: 13, color: C.dim, marginTop: 8 }}>{untag(claim.note)}</div> : null}
    </Box>)
}

/** CR 84 · the subscriptions list: service · price · renews (from the receipt — "expected" when the email doesn't say); tap one → its
 *  cancel flow (Sasha 243: moved here from CR 84's S2App so /next draws it too). */
export function SubscriptionsCard({ items, total, source, send }: { items: Ev[]; total?: string; source?: string; send: (t: string) => void }) {
  const per: Record<string, string> = { monthly: '/mo', yearly: '/yr', weekly: '/wk', quarterly: '/qtr' }
  return (
    <Box k="Subscriptions" h={subsHeading(items, total ? untag(total) : total)}>{/* Sasha 246 · none found → "No subscriptions found" */}
      {items.length === 0 ? <div style={{ fontSize: 14.5, color: C.dim }}>No subscription receipts found.</div> : items.map((s, i) => (
        <button key={s.subscription_id || i} onClick={() => send(`Cancel ${s.service}`)} style={{ display: 'flex', width: '100%', justifyContent: 'space-between', gap: 12,
          background: 'transparent', border: 'none', borderTop: i ? `1px solid ${C.line}` : 'none', color: 'inherit', padding: '9px 0',
          textAlign: 'left', cursor: 'pointer', fontSize: 15 }}>
          <span style={{ fontWeight: 600 }}>{untag(String(s.service))}</span>
          <span style={{ color: C.dim, fontSize: 14, textAlign: 'right' }}>{untag(String(s.price))}{per[s.how_often] || ''}
            {s.renews ? <> · renews {untag(String(s.renews))}{s.expected ? ' (expected)' : ''}</> : null}
            {s.not_yet ? <span style={{ display: 'block', color: C.gold, fontSize: 12.5 }}>{untag(String(s.not_yet))}</span> : null}</span>
        </button>))}
      <div style={{ fontSize: 12.5, color: C.dim, marginTop: 6 }}>{subsFooter(items, untag(source || 'your receipts'))}</div>{/* Sasha 246 · "tap one" only over a list */}
    </Box>)
}

/** Sasha 248 · "fill it now": their OWN booking page, with every detail to copy in one tap — they press confirm there. */
export function PreparedCard({ ev }: { ev: Ev }) {
  const [copied, setCopied] = useState<string | null>(null)
  const copy = (label: string, value: string) => {
    navigator.clipboard?.writeText(value).then(() => { setCopied(label); setTimeout(() => setCopied(null), 1500) }).catch(() => {})
  }
  return (
    <Box k="Ready to book" h={untag(String(ev.venue || 'Their booking page'))} tone={C.gold}>
      {(ev.fields || []).map((f: Ev) => (
        <div key={f.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, padding: '6px 0', borderTop: `1px solid ${C.line}` }}>
          <span><span style={{ color: C.dim, fontSize: 12.5 }}>{f.label}</span><br /><span style={{ fontSize: 15 }}>{untag(String(f.value))}</span></span>
          <button type="button" onClick={() => copy(f.label, String(f.value))} style={{ padding: '5px 12px', borderRadius: 999, border: `1px solid ${C.gold}`, background: 'transparent', color: C.gold, fontWeight: 700 }}>
            {copied === f.label ? 'Copied' : 'Copy'}</button>
        </div>))}
      <a href={ev.url} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 10, padding: '10px 18px', borderRadius: 999, background: C.gold, color: '#111', fontWeight: 800, textDecoration: 'none' }}>Open their booking page</a>
      <div style={{ fontSize: 12.5, color: C.dim, marginTop: 8 }}>{ev.on_phone ? 'Also sent to your phone. ' : ''}You press confirm there — it&apos;s booked only when their page says so.</div>
    </Box>)
}

/** Sasha 241 · the render kinds these cards draw (sasha.py's former KINDS_S2_ONLY): one render event → its card, for /next. */
export const SHARED_KINDS = ['keep_capture', 'capabilities', 'plans', 'notice', 'counter_card', 'my_cards', 'accident', 'claim_status', 'wa_open', 'activities', 'subscriptions', 'prepared']   // Sasha 243 · + CR 84's list

export function SharedCard({ ev, send }: { ev: Ev; send: (t: string) => void }) {
  if (ev.kind === 'keep_capture') return <KeepCapture what={ev.what === 'loyalty' ? 'loyalty' : 'passport'} />
  if (ev.kind === 'plans' && Array.isArray(ev.items)) return <Plans items={ev.items} on={ev.on} />
  if (ev.kind === 'counter_card' && ev.card) return <CounterCard card={ev.card} />
  if (ev.kind === 'my_cards') return <MyCards cards={ev.cards || []} choose={send} />
  if (ev.kind === 'accident' && ev.view) return <AccidentCard view={ev.view} send={send} />
  if (ev.kind === 'claim_status' && ev.claim) return <ClaimStatus claim={ev.claim} />
  if (ev.kind === 'wa_open' && typeof ev.open === 'string' && ev.open.startsWith('https://wa.me/'))
    return <WaOpen c={{ to: ev.to || {}, text: String(ev.text || ''), open: ev.open, why: String(ev.why || '') }} />
  // Sasha 252 · things to do are places: the ONE place card and sheet (ActivityCard retired — EU 251 FAIL 5, Tyler's ruling)
  if (ev.kind === 'activities' && Array.isArray(ev.cards)) return (<><div style={{ display: 'flex', gap: 10, overflowX: 'auto', maxWidth: '100%', padding: '4px 2px 8px' }}>
    {ev.cards.map((a: Ev) => <PlaceCard key={a.place_id} card={a} onBook={(name: string) => send(`${name}, please`)} />)}</div>
    {(ev.unread || []).length ? <div style={{ fontSize: 13, color: C.dim, margin: '4px 2px' }}>Couldn&apos;t check on their official sites: {ev.unread.map(untag).join(', ')}</div> : null}</>)
  if (ev.kind === 'prepared' && typeof ev.url === 'string' && /^https:\/\//.test(ev.url)) return <PreparedCard ev={ev} />   // Sasha 248
  if (ev.kind === 'subscriptions' && Array.isArray(ev.items)) return <SubscriptionsCard items={ev.items} total={ev.total} source={ev.source} send={send} />
  if (ev.kind === 'notice' && ev.title) return (
    <Box k={ev.status ? untag(ev.status) : 'Update'} h={untag(ev.title)}>
      {(ev.lines || []).map((l: string, i: number) => <div key={i} style={{ fontSize: 14.5, padding: '2px 0', color: 'rgba(255,255,255,.88)' }}>{untag(l)}</div>)}
    </Box>)
  if (ev.kind === 'capabilities' && Array.isArray(ev.groups)) return (
    <Box k="What I can do">
      {ev.groups.map((g: Ev) => (
        <div key={g.group} style={{ marginTop: 8 }}>
          <div style={{ fontWeight: 700, color: C.gold, fontSize: 14 }}>{g.group}</div>
          {(g.items || []).map((i: string) => <div key={i} style={{ fontSize: 14.5, padding: '2px 0', color: 'rgba(255,255,255,.88)' }}>{i}</div>)}
        </div>))}
    </Box>)
  return null
}
