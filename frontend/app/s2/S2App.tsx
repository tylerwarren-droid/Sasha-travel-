'use client'
/**
 * Sasha 221 · S2 — SASHA, the personal concierge, phone first (390×844 first; works on a desktop). Her own front door, beside S1
 * (/next), sharing the engine: the same agent (through /api/s2-agent, which says "S2"), the same records and the same safety.
 *   · sign-in with the 6-digit code (/sign-in?next=/s2)
 *   · Home: her greeting, a big mic (Deepgram), a text box
 *   · the conversation with its cards: places, the read-back, booked, the calendar, the email, the payment ("Pay here")
 *   · Activity: everything she did, each line with its proof
 *   · her voice: what she says is spoken (TTS) once the person has used the mic or turned her voice on; no avatar on S2 v1
 * Nothing shown here carries a "test" or "stand-in" label (lib/no-test-label.mjs) — what's underneath is unchanged.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import VoiceButton from '@/app/components/VoiceButton'
import { PayHere } from '@/app/components/PayHere'
import { untag, untagDeep } from '@/lib/no-test-label.mjs'
import { apiHeaders, apiUrl } from '@/lib/api'

type Card =
  | { k: 'venues'; cards: { place_id: string; name: string; rating?: number; rating_count?: number; area?: string; address?: string; type?: string; photo?: string; open_at?: string }[] }
  | { k: 'read_back'; lines: string[]; what?: string; live?: boolean; status?: string; total?: number }
  | { k: 'calendar'; title?: string; links: Record<string, string> }
  | { k: 'pay'; client_secret?: string; url?: string; total_eur?: number; already_paid?: boolean }
  | { k: 'booked'; line: string }
  | { k: 'keep_capture'; what: 'passport' | 'loyalty' }
  | { k: 'counter_card'; card: Ev }   // CR 75 · fine print: the counter card (each line quoted)
  | { k: 'my_cards'; cards: { product: string; network: string; status: string }[] }
  | { k: 'accident'; view: Ev }
  | { k: 'claim_status'; claim: Ev }
type Msg = { role: 'user' | 'sasha'; text: string; cards: Card[] }
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- a stream event, shaped by its own `type` (agent/sasha.py)
type Ev = Record<string, any>
type Item = { kind: string; state: string; check: 'green' | 'red' | 'amber'; line: string; at: string; ref: string; about?: string; proof?: { reference?: string } }

/** The first n sentences — a card's headline, not her whole reply. */
function firstSentences(t: string, n: number): string {
  const parts = t.match(/[^.!?]+[.!?]+(\s|$)/g)
  return parts ? parts.slice(0, n).join('').trim() : t
}

const GREETING = 'Hey there — what can I do for you?'

/** The cards the person sees — as the backend's own shown_cards (agapi/venues.py): the ranking's default order, its `show` count. */
function shownCards(preset: Ev): Extract<Card, { k: 'venues' }>['cards'] {
  if (Array.isArray(preset.cards) && preset.cards.length) return preset.cards
  const all = (Array.isArray(preset.all) ? preset.all : []).filter((c: Ev) => c && c.place_id)
  const rk = preset.ranking || {}
  const order: string[] | undefined = (rk.orders || {})[rk.default || 'rated']
  const by = new Map(all.map((c: Ev) => [c.place_id, c]))
  const cards = order ? order.map(i => by.get(i)).filter(Boolean) : all
  return (cards as Extract<Card, { k: 'venues' }>['cards']).slice(0, Number(preset.show) || 5)
}
const C = { bg: '#0b0b10', card: '#16151d', line: 'rgba(255,255,255,.1)', gold: '#E8B923', dim: 'rgba(255,255,255,.6)' }

function useSignedIn(): boolean | null {
  const [ok, setOk] = useState<boolean | null>(null)
  useEffect(() => {
    fetch('/api/sasha-agent/activity', { cache: 'no-store' }).then(r => setOk(r.ok)).catch(() => setOk(false))
  }, [])
  return ok
}

function Speaker() {
  const q = useRef<string[]>([])
  const playing = useRef(false)
  const on = useRef(false)
  const next = useCallback(async () => {
    if (playing.current || !q.current.length) return
    playing.current = true
    const text = q.current.shift() as string
    try {
      const r = await fetch(apiUrl('/api/voice/tts'), { method: 'POST', headers: { ...apiHeaders(), 'content-type': 'application/json' }, body: JSON.stringify({ text }) })
      if (r.ok) {
        const a = new Audio(URL.createObjectURL(await r.blob()))
        await new Promise<void>(res => { a.onended = () => res(); a.onerror = () => res(); a.play().catch(() => res()) })
      }
    } catch { /* her words are on screen either way */ }
    playing.current = false
    next()
  }, [])
  return {
    unlock: () => { on.current = true; try { new Audio().play().catch(() => {}) } catch { /* iOS: a gesture unlocks audio */ } },
    say: (t: string) => { if (on.current && t.trim()) { q.current.push(t); next() } },
    get on() { return on.current },
  }
}

function VenueCards({ cards, choose }: { cards: Extract<Card, { k: 'venues' }>['cards']; choose: (name: string) => void }) {
  return (
    <div style={{ display: 'flex', gap: 10, overflowX: 'auto', maxWidth: '100%', padding: '4px 2px 8px', scrollSnapType: 'x mandatory' }}>
      {cards.map(c => (
        <div key={c.place_id} style={{ minWidth: 230, maxWidth: 230, background: C.card, border: `1px solid ${C.line}`, borderRadius: 16, overflow: 'hidden', scrollSnapAlign: 'start' }}>
          {/* eslint-disable-next-line @next/next/no-img-element -- a remote venue photo, sized by the card */}
          {c.photo ? <img src={c.photo} alt="" style={{ width: '100%', height: 120, objectFit: 'cover', display: 'block' }} /> : null}
          <div style={{ padding: 12 }}>
            <div style={{ fontWeight: 700 }}>{untag(c.name)}</div>
            <div style={{ fontSize: 13, color: C.dim, marginTop: 2 }}>
              {c.rating ? `★ ${c.rating}${c.rating_count ? ` (${Number(c.rating_count).toLocaleString()})` : ''} · ` : ''}{untag(c.area || c.type || '')}
            </div>
            {typeof c.open_at === 'string' ? <div style={{ fontSize: 12.5, color: C.dim, marginTop: 2 }}>{untag(c.open_at)}</div> : null}
            <button onClick={() => choose(untag(c.name))} style={{ marginTop: 10, padding: '8px 14px', borderRadius: 999, border: `1px solid ${C.gold}`, background: 'transparent', color: C.gold, fontWeight: 700 }}>Choose</button>
          </div>
        </div>
      ))}
    </div>
  )
}

function Box({ k, h, children, tone }: { k: string; h?: string; children?: React.ReactNode; tone?: string }) {
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
async function shrink(file: File): Promise<string> {
  const bmp = await createImageBitmap(file)
  const scale = Math.min(1, 1800 / Math.max(bmp.width, bmp.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bmp.width * scale); canvas.height = Math.round(bmp.height * scale)
  canvas.getContext('2d')?.drawImage(bmp, 0, 0, canvas.width, canvas.height)
  bmp.close?.()
  return canvas.toDataURL('image/jpeg', 0.88).split(',')[1] ?? ''
}

function KeepCapture({ what }: { what: 'passport' | 'loyalty' }) {
  type Phase = { p: 'pick' } | { p: 'reading' } | { p: 'confirm'; token: string; shown: string[] } | { p: 'saving' } | { p: 'saved'; item: string } | { p: 'error'; why: string }
  const [ph, setPh] = useState<Phase>({ p: 'pick' })
  const input = useRef<HTMLInputElement | null>(null)
  const label = what === 'passport' ? "your passport's photo page" : 'your card, or its Apple Wallet screenshot'
  async function picked(f?: File | null) {
    if (!f) return
    setPh({ p: 'reading' })
    try {
      const image = await shrink(f)
      const r = await fetch('/api/s2-keep/scan', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ kind: what, image, media_type: 'image/jpeg' }) })
      const j = await r.json().catch(() => ({}))
      setPh(j?.ok ? { p: 'confirm', token: j.token, shown: j.shown || [j.masked] } : { p: 'error', why: j?.message || 'That photo couldn\u2019t be read.' })
    } catch { setPh({ p: 'error', why: 'That photo couldn\u2019t be read.' }) }
    if (input.current) input.current.value = ''
  }
  async function act(token: string, action: 'confirm' | 'discard') {
    if (action === 'discard') { fetch(`/api/s2-keep/scan/${encodeURIComponent(token)}/discard`, { method: 'POST' }).catch(() => {}); setPh({ p: 'pick' }); return }
    setPh({ p: 'saving' })
    const r = await fetch(`/api/s2-keep/scan/${encodeURIComponent(token)}/confirm`, { method: 'POST' }).catch(() => null)
    const j = r ? await r.json().catch(() => ({})) : {}
    setPh(j?.ok ? { p: 'saved', item: j.item } : { p: 'error', why: j?.message || 'It wasn\u2019t saved — try again.' })
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

/** CR 75 · fine print — every line rests on a quote; "source" opens the sentence, its page and the date it was read. */
type Q = { quote: string; source_url: string; read_at?: string }
function Sources({ quotes }: { quotes?: Q[] }) {
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
function Lines({ title, lines, tone }: { title: string; lines?: Line[]; tone?: string }) {
  if (!lines || !lines.length) return null
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 11.5, letterSpacing: '.1em', textTransform: 'uppercase', color: tone || C.dim }}>{title}</div>
      {lines.map((l, i) => <div key={i} style={{ fontSize: 14.5, padding: '3px 0' }}>{untag(l.say)}<Sources quotes={l.quotes} /></div>)}
    </div>)
}
function CounterCard({ card }: { card: Ev }) {
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
function MyCards({ cards, choose }: { cards: { product: string; network: string; status: string }[]; choose: (t: string) => void }) {
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
function AccidentCard({ view, send }: { view: Ev; send: (t: string) => void }) {
  const [v, setV] = useState<Ev>(view)
  const [busy, setBusy] = useState<string | null>(null)
  const pick = useRef<HTMLInputElement | null>(null)
  const shot = useRef<string>('')
  useEffect(() => setV(view), [view])
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
function ClaimStatus({ claim }: { claim: Ev }) {
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

function CardView({ c, choose, send }: { c: Card; choose: (t: string) => void; send: (t: string) => void }) {
  if (c.k === 'counter_card') return <CounterCard card={c.card} />
  if (c.k === 'my_cards') return <MyCards cards={c.cards} choose={choose} />
  if (c.k === 'accident') return <AccidentCard view={c.view} send={send} />
  if (c.k === 'claim_status') return <ClaimStatus claim={c.claim} />
  if (c.k === 'keep_capture') return <KeepCapture what={c.what} />
  if (c.k === 'venues') return <VenueCards cards={c.cards} choose={choose} />
  if (c.k === 'booked') return <Box k="Booked" h={firstSentences(untag(c.line.replace(/^✅\s*/, '').replace(/^Booked:\s*/i, '')), 2)} tone="rgba(126,226,168,.5)" />
  if (c.k === 'calendar') return (
    <Box k="Add to your calendar" h={untag(c.title || 'Your booking')}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {(['google', 'outlook', 'apple'] as const).filter(x => c.links[x]).map(x => (
          <a key={x} href={c.links[x]} target="_blank" rel="noreferrer" style={{ padding: '8px 14px', borderRadius: 999, border: `1px solid ${C.gold}`, color: C.gold, fontWeight: 600, textDecoration: 'none' }}>
            {x === 'google' ? 'Google' : x === 'outlook' ? 'Outlook' : 'Apple / other'}</a>))}
      </div>
    </Box>)
  if (c.k === 'pay') return <div style={{ background: C.card, border: `1px solid ${C.gold}`, borderRadius: 16, padding: 14, marginTop: 8 }}><PayHere clientSecret={c.client_secret} url={c.url} totalEur={c.total_eur} alreadyPaid={c.already_paid} /></div>
  const head = c.what ? (c.status === 'sent' ? 'Sent' : c.status === 'not_sent' ? 'Not sent' : 'Ready to send · on your yes')
    : (c.total ? `Ready to book · €${Math.round(c.total).toLocaleString()} all in` : 'Ready to book · on your yes')
  return (
    <Box k={head} h={c.what === 'email' ? (c.live ? "From Sasha's own address" : 'Kept here · not sent') : c.what === 'whatsapp' ? "From Sasha's own number" : undefined}>
      {c.lines.filter(l => !/^\s*⚠/.test(l)).map((l, i) => <div key={i} style={{ fontSize: 14.5, padding: '2px 0', color: 'rgba(255,255,255,.88)' }}>{untag(l)}</div>)}
    </Box>)
}

function Activity() {
  const [items, setItems] = useState<Item[] | null>(null)
  useEffect(() => {
    fetch('/api/sasha-agent/activity', { cache: 'no-store' }).then(r => r.json()).then(j => setItems(untagDeep(j.items ?? []))).catch(() => setItems([]))
  }, [])
  if (!items) return <p style={{ padding: 24, color: C.dim }}>Loading…</p>
  if (!items.length) return <p style={{ padding: 24, color: C.dim }}>Nothing yet today. When Sasha books, sends or adds something for you, it’s listed here with its proof.</p>
  const tone = { green: '#7ee2a8', red: '#f19999', amber: C.gold }
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: '8px 16px' }}>
      {items.map(i => (
        <li key={i.ref + i.line} style={{ display: 'flex', gap: 12, padding: '12px 0', borderBottom: `1px solid ${C.line}` }}>
          <span style={{ width: 34, height: 34, flex: 'none', borderRadius: '50%', display: 'grid', placeItems: 'center', background: tone[i.check] || C.gold, color: '#111', fontWeight: 800 }}>
            {i.check === 'green' ? '✓' : i.check === 'red' ? '✕' : '…'}</span>
          <div><div style={{ fontWeight: 600 }}>{i.line}{i.about ? ` · ${i.about}` : ''}</div>
            {i.proof?.reference ? <div style={{ fontSize: 12.5, color: C.dim }}>Ref {i.proof.reference}</div> : null}
            <div style={{ fontSize: 12.5, color: C.dim }}>{new Date(i.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</div></div>
        </li>))}
    </ul>
  )
}

export default function S2App() {
  const signedIn = useSignedIn()
  const [tab, setTab] = useState<'sasha' | 'activity'>('sasha')
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const session = useRef('')
  useEffect(() => { session.current = `s2-${Date.now().toString(36)}-${crypto.randomUUID().slice(0, 8)}` }, [])
  const speaker = useRef(Speaker()).current
  const end = useRef<HTMLDivElement>(null)
  const histRef = useRef<{ role: string; content: string }[]>([])

  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [msgs])
  useEffect(() => {   // a payment settled (Pacioli): said here, and the pay card turns to Paid
    if (!signedIn) return
    const es = new EventSource('/api/sasha-agent/events?since=0')
    es.onmessage = m => {
      let ev: Ev
      try { ev = untagDeep(JSON.parse(m.data)) } catch { return }
      if (ev.type !== 'booked' && ev.type !== 'booking_failed') return
      setMsgs(ms => [...ms.map(x => ({ ...x, cards: x.cards.map(c => (c.k === 'pay' ? { ...c, already_paid: ev.type === 'booked' } : c)) })),
                     { role: 'sasha', text: String(ev.say || ev.text || ''), cards: [] }])
    }
    return () => es.close()
  }, [signedIn])

  const send = useCallback(async (text: string) => {
    const t = text.trim()
    if (!t || busy) return
    setBusy(true)
    setInput('')
    setMsgs(ms => [...ms, { role: 'user', text: t, cards: [] }, { role: 'sasha', text: '', cards: [] }])
    const patch = (f: (m: Msg) => Msg) => setMsgs(ms => { const c = ms.slice(); c[c.length - 1] = f(c[c.length - 1]); return c })
    let reply = ''
    try {
      const r = await fetch('/api/s2-agent', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ message: t, history: histRef.current.slice(-30), session_id: session.current }) })
      if (r.status === 401) { window.location.href = '/sign-in?next=/s2'; return }
      const rd = r.body?.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (rd) {
        const { done, value } = await rd.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let i
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const line = buf.slice(0, i).replace(/^data: /, ''); buf = buf.slice(i + 2)
          let ev: Ev
          try { ev = JSON.parse(line) } catch { continue }
          if (ev.type === 'render' || ev.type === 'state') ev = untagDeep(ev)
          if (ev.type === 'text') { reply += ev.delta; patch(m => ({ ...m, text: untag(reply) })) }
          else if (ev.type === 'say') speaker.say(ev.text)
          else if (ev.type === 'replace') { reply = ev.text; patch(m => ({ ...m, text: untag(reply) })); if (ev.speak && ev.say) speaker.say(ev.say) }
          else if (ev.type === 'error') { reply = ev.message; patch(m => ({ ...m, text: untag(reply) })); speaker.say(ev.message) }
          else if (ev.type === 'done') { reply = ev.text || reply; patch(m => ({ ...m, text: untag(reply), cards: /^✅\s*Booked/m.test(reply) ? [...m.cards, { k: 'booked', line: (reply.match(/✅[^\n]*/) || [''])[0] }] : m.cards })) }
          else if (ev.type === 'render') {
            const add = (c: Card) => patch(m => ({ ...m, cards: [...m.cards.filter(x => x.k !== c.k), c] }))
            if (ev.kind === 'venues' && ev.preset) { const cs = shownCards(ev.preset); if (cs.length) add({ k: 'venues', cards: cs }) }
            else if (ev.kind === 'read_back' && Array.isArray(ev.read_back)) add({ k: 'read_back', lines: ev.read_back, what: ev.what, live: ev.live, status: ev.status, total: ev.total_eur })
            else if (ev.kind === 'calendar' && ev.links) add({ k: 'calendar', title: ev.title, links: ev.links })
            else if (ev.kind === 'keep_capture') add({ k: 'keep_capture', what: ev.what === 'loyalty' ? 'loyalty' : 'passport' })
            else if (ev.kind === 'pay_here') add({ k: 'pay', client_secret: ev.client_secret, url: ev.url, total_eur: ev.total_eur, already_paid: ev.already_paid })
            else if (ev.kind === 'counter_card' && ev.card) add({ k: 'counter_card', card: ev.card })   // CR 75 · fine print
            else if (ev.kind === 'my_cards') add({ k: 'my_cards', cards: ev.cards || [] })
            else if (ev.kind === 'accident' && ev.view) add({ k: 'accident', view: ev.view })
            else if (ev.kind === 'claim_status' && ev.claim) add({ k: 'claim_status', claim: ev.claim })
          }
        }
      }
    } catch {
      patch(m => ({ ...m, text: m.text || 'I lost the connection there — say it once more?' }))
    } finally {
      histRef.current = [...histRef.current, { role: 'user', content: t }, { role: 'assistant', content: reply }]
      setBusy(false)
    }
  }, [busy, speaker])

  if (signedIn === null) return <main style={{ minHeight: '100dvh', background: C.bg }} />
  if (!signedIn) return (
    <main style={{ minHeight: '100dvh', background: C.bg, color: '#fff', display: 'grid', placeItems: 'center', padding: 24, fontFamily: 'system-ui' }}>
      <div style={{ textAlign: 'center', maxWidth: 340 }}>
        <div style={{ fontSize: 34, fontWeight: 700, fontFamily: "'Playfair Display',Georgia,serif" }}>Sasha</div>
        <p style={{ color: C.dim, marginTop: 8 }}>Your personal concierge. Sign in with your email — a 6-digit code, right here.</p>
        <a href="/sign-in?next=/s2" style={{ display: 'inline-block', marginTop: 18, padding: '12px 22px', borderRadius: 999, background: C.gold, color: '#111', fontWeight: 700, textDecoration: 'none' }}>Sign in</a>
      </div>
    </main>)

  return (
    <main style={{ minHeight: '100dvh', background: C.bg, color: '#fff', display: 'flex', flexDirection: 'column', fontFamily: 'system-ui', maxWidth: 560, width: '100%', margin: '0 auto', overflowX: 'hidden' }}>
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 16px', paddingTop: 'max(56px, calc(env(safe-area-inset-top) + 44px))' }}>{/* room for the site's sign-in badge above */}
        <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "'Playfair Display',Georgia,serif" }}>Sasha</div>
        <nav style={{ display: 'flex', gap: 6 }}>
          {(['sasha', 'activity'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ padding: '7px 14px', borderRadius: 999, border: `1px solid ${tab === t ? C.gold : C.line}`, background: 'transparent', color: tab === t ? C.gold : C.dim, fontWeight: 600 }}>
              {t === 'sasha' ? 'Sasha' : 'Activity'}</button>))}
        </nav>
      </header>
      {tab === 'activity' ? <Activity /> : (
        <>
          <section style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', minWidth: 0, padding: '0 16px 12px' }}>
            {msgs.length === 0 ? (
              <div style={{ textAlign: 'center', paddingTop: '18vh' }}>
                <div style={{ fontSize: 28, fontWeight: 600, fontFamily: "'Playfair Display',Georgia,serif", lineHeight: 1.25 }}>{GREETING}</div>
                <p style={{ color: C.dim, marginTop: 10 }}>A table tonight, a spa on Saturday, an email to someone, a booking in your calendar.</p>
              </div>
            ) : msgs.map((m, i) => (
              <div key={i} style={{ margin: '10px 0', minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                {m.text || m.role === 'user' ? (
                  <div style={{ maxWidth: '88%', padding: '10px 14px', borderRadius: 18, background: m.role === 'user' ? 'linear-gradient(135deg,#6d4aff,#9b4dff)' : C.card, border: m.role === 'user' ? 'none' : `1px solid ${C.line}`, lineHeight: 1.45 }}>
                    {m.text}</div>
                ) : <div style={{ color: C.dim, padding: '8px 4px' }}>…</div>}
                {m.cards.length ? <div style={{ width: '100%', minWidth: 0, maxWidth: '100%' }}>{m.cards.map((c, j) => <CardView key={j} c={c} choose={t => send(`${t}, please.`)} send={send} />)}</div> : null}
              </div>))}
            <div ref={end} />
          </section>
          <footer style={{ padding: '10px 12px', paddingBottom: 'max(12px, env(safe-area-inset-bottom))', borderTop: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className="s2-mic" onPointerDown={() => speaker.unlock()} style={{ flex: 'none' }}>
              <VoiceButton onTranscript={send} readyToListen muted={busy} />
            </div>
            <form onSubmit={e => { e.preventDefault(); send(input) }} style={{ flex: 1, display: 'flex', gap: 8 }}>
              <input value={input} onChange={e => setInput(e.target.value)} placeholder="Ask Sasha anything…" aria-label="Message Sasha"
                style={{ flex: 1, minWidth: 0, padding: '12px 14px', borderRadius: 999, border: `1px solid ${C.line}`, background: C.card, color: '#fff', fontSize: 16 }} />
              <button type="submit" disabled={busy || !input.trim()} aria-label="Send"
                style={{ padding: '0 16px', borderRadius: 999, border: 0, background: C.gold, color: '#111', fontWeight: 700, opacity: busy || !input.trim() ? 0.5 : 1 }}>➤</button>
            </form>
          </footer>
          <style>{`.s2-mic button{width:56px;height:56px;border-radius:50%}`}</style>
        </>
      )}
    </main>
  )
}
