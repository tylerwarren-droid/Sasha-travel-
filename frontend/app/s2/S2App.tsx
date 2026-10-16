'use client'
/**
 * Sasha 221 · S2 — SASHA, the personal concierge, phone first (390×844 first; works on a desktop). Her own front door, beside S1
 * (/next), sharing the engine: the same agent (through /api/s2-agent, which says "S2"), the same records and the same safety.
 *   · sign-in with the 6-digit code (/sign-in?next=/s2)
 *   · Home: her greeting, a big mic (Deepgram), a text box
 *   · the conversation with its cards: places, the read-back, booked, the calendar, the email, the payment ("Pay here")
 *   · Activity: everything she did, each line with its proof
 *   · her voice: what she says is spoken (TTS) once the person has used the mic or turned her voice on; her face on screen as she speaks (S2Hello; Sasha 232)
 * Nothing shown here carries a "test" or "stand-in" label (lib/no-test-label.mjs) — what's underneath is unchanged.
 */
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import VoiceButton, { type VoiceCtl } from '@/app/components/VoiceButton'
import { reappear, voiceOf } from '@/lib/presence-rule.mjs'
import { midFlow } from '@/lib/greeting-rule.mjs'   // Sasha 274 · mid-booking, from the screen   // Sasha 273 · rule 4 and the mic's truth: the ONE presence rule
import { AccountControl, SIGN_IN_CARRY } from '@/app/components/SignedInLine'   // Sasha 257 · who is signed in, quietly in the header
import { PayHere } from '@/app/components/PayHere'
import S2Hello, { type HelloCtl } from './S2Hello'
import { KeepScreen } from '@/app/keep/KeepScreen'   // Sasha 235 · My Keep
// Sasha 241 · the cards moved to components/cards/ (shared with /next's SashaChat), unchanged
import { PlaceCard } from '@/app/components/cards/PlaceCard'   // Sasha 248 · one place card
import { C, Box, shrink, KeepCapture, WaOpen, Plans, CounterCard, MyCards, AccidentCard, ClaimStatus, SubscriptionsCard, PreparedCard } from '@/app/components/cards/S2Cards'
import type { Plan } from '@/app/components/cards/S2Cards'
export { KeepCapture }   // Sasha 228's handoff page imports it from here
import TripPanel from '@/app/components/workspace/TripPanel'   // Sasha 236 · the trip board: S1's own, on the same records
import { TRIP_BOARD_CSS } from './tripBoardCss'
import { untag, untagDeep } from '@/lib/no-test-label.mjs'
import { apiHeaders, apiUrl } from '@/lib/api'
import SleepButton from '@/app/components/SleepButton'   // Sasha 246 item 2 · pause / sleep
import { sleepStep, HERE, ASLEEP, AWAKE, ASLEEP_LINE } from '@/lib/sleep-rule.mjs'
import { loadFirstLine, isWork, takeFirstLine, forgetAcks, cameraOffLine } from '@/lib/first-line'
import { BLOCKED, stepsFor } from '@/lib/mic-state'
import { holdPlayAndRecord } from '@/lib/audio-session'   // Sasha 267 · the page's one audio session   // Sasha 266 · the mic's stuck state, said with its steps   // Sasha 265 · item 5: the first line, at once
import { CHIPS } from '@/lib/capabilities.generated.mjs'   // Sasha 249 · one capability list
import { actingOf } from '@/lib/acting-rule.mjs'   // Sasha 249 · whoami's acting

type Card =
  | { k: 'venues'; cards: { place_id: string; name: string; rating?: number; rating_count?: number; area?: string; address?: string; type?: string; photo?: string; open_at?: string }[] }
  | { k: 'read_back'; lines: string[]; what?: string; live?: boolean; status?: string; total?: number; act?: string
      ask?: string; choices?: { title: string; route: string }[]; read_back_id?: string }   // Sasha 265 · item 4: the call's card IS the question
  | { k: 'calendar'; title?: string; links: Record<string, string> }
  | { k: 'pay'; client_secret?: string; url?: string; total_eur?: number; already_paid?: boolean }
  | { k: 'booked'; line: string }
  | { k: 'keep_capture'; what: 'passport' | 'loyalty' }
  | { k: 'wa_open'; to: { name?: string | null; number?: string }; text: string; open: string; why: string }   // Sasha 230
  | { k: 'capabilities'; groups: { group: string; items: string[] }[] }
  | { k: 'plans'; items: Plan[]; on?: string }
  | { k: 'notice'; title: string; lines: string[]; status?: string }
  | { k: 'counter_card'; card: Ev }   // CR 75 · fine print: the counter card (each line quoted)
  | { k: 'my_cards'; cards: { product: string; network: string; status: string }[] }
  | { k: 'accident'; view: Ev }
  | { k: 'claim_status'; claim: Ev }
  | { k: 'handover'; url: string; external: boolean }   // Sasha 236 · Tap to finish (their page / our hand-over), over her
  | { k: 'trip'; what: string }                          // Sasha 236 · the trip changed: one tap to the Trip board
  | { k: 'activities'; cards: Ev[]; unread: string[]; date?: string }   // CR 81 · things to do, verified on each place's own site
  | { k: 'prepared'; ev: Ev }   // Sasha 248 · "fill it now": their page + the details to copy
  | { k: 'subscriptions'; items: Ev[]; total?: string; source?: string }   // CR 84 · what they pay for, from their receipts
  | { k: 'sign_in' }   // Sasha 274 · a guest's booking: sign in to book for real (this conversation kept)
  | { k: 'no_answer'; act_id: string; ask?: string; choices: { id: string; label: string; page?: string }[]; page?: string }   // Sasha 269 · AgAPI's
const NOT_CLEARED = 'I couldn’t clear our conversation just now — it’s still here, and I still remember it. Try New chat again in a moment.'   // Sasha 265 · item 3
type Msg = { role: 'user' | 'sasha'; text: string; cards: Card[]; hold?: string; restored?: boolean }   // Sasha 257 · hold: the holding line, until her words come
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- a stream event, shaped by its own `type` (agent/sasha.py)
type Ev = Record<string, any>
/** Sasha 249 · ONE STATUS: a `booked` event's card line — the server's status (agapi/s2_status.py), shown only when it says booked */
const bookedLine = (ev: Ev): string | null =>
  ev?.status && ['booked', 'partly_booked'].includes(String(ev.status.state)) && ev.status.line ? String(ev.status.line) : null
type Item = { kind: string; state: string; check: 'green' | 'red' | 'amber'; line: string; at: string; ref: string; about?: string; proof?: { reference?: string } }

/** The first n sentences — a card's headline, not her whole reply. */
function firstSentences(t: string, n: number): string {
  const parts = t.match(/[^.!?]+[.!?]+(\s|$)/g)
  return parts ? parts.slice(0, n).join('').trim() : t
}

const GREETING = 'Hey there — what can I do for you?'
/** Sasha 273 · item 4 · LAST ACTIVITY: the conversation's last turn — the server's (s2-memory's last_at, every device) and this page's
 *  own sends and taps since. This browser keeps its own last one so a reload can answer rule 4 before the server does — only ever to
 *  say "recent" (the server's is never older than it), never to skip the server's answer. */
const LAST_KEY = 's2_last_at'
const localLastAt = (): number | null => { try { const v = Number(localStorage.getItem(LAST_KEY)); return v > 0 ? v : null } catch { return null } }
const noSub = () => () => {}
/** Sasha 274 · item 1: the build this page was made from (next.config env) — compared with /api/version's. */
const BUILD = process.env.NEXT_PUBLIC_BUILD || 'dev'
const CARRY = 's2_carry'
type Carry = { msgs: Msg[]; hist: { role: string; content: string }[] }
/** The conversation, across a reload for a new release — this tab only, read once, never a payment card. */
function putCarry(msgs: Msg[], hist: { role: string; content: string }[], key: string = CARRY): void {
  try { sessionStorage.setItem(key, JSON.stringify({ at: Date.now(), msgs: msgs.slice(-40).map(m => ({ ...m, hold: undefined, cards: m.cards.filter(c => c.k !== 'pay' && c.k !== 'sign_in') })), hist: hist.slice(-30) })) } catch { /* private mode: recall restores what it can */ }
}
function takeCarry(): Carry | null {
  try {
    // Sasha 274 · rows 1063/1064: a guest's own sign-in carries their conversation too (20 min: the code can take a while to arrive)
    const signIn = sessionStorage.getItem(SIGN_IN_CARRY); sessionStorage.removeItem(SIGN_IN_CARRY)
    const raw = sessionStorage.getItem(CARRY) || signIn; sessionStorage.removeItem(CARRY)
    const j = raw ? JSON.parse(raw) : null
    return j && Date.now() - Number(j.at) < (raw === signIn ? 20 * 60000 : 120000) && Array.isArray(j.msgs) ? { msgs: j.msgs.map((m: Msg) => ({ ...m, restored: true })), hist: Array.isArray(j.hist) ? j.hist : [] } : null
  } catch { return null }
}
const tzNow = (): string | undefined => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone } catch { return undefined } }
/** Sasha 257 · a reply stream silent this long is stopped and said (her longest tool turns stream within it) — never "busy" for ever */
const STALL_MS = 75000

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

/** Sasha 249 · ONE IDENTITY: signed in = whoami names someone ACTING (the same answer the badge renders) — not a second
 *  decision from an activity ping that could fail for other reasons. */
/** Sasha 274 · who is acting (whoami's own answer) — a guest's booking offers sign-in in the conversation */
let ACTING: 'user' | 'founder' | 'guest' | null = null
function useSignedIn(): boolean | null {
  const [ok, setOk] = useState<boolean | null>(null)
  useEffect(() => {
    fetch('/api/auth/whoami', { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null).then(w => { ACTING = actingOf(w); setOk(ACTING !== null) }).catch(() => setOk(false))
  }, [])
  return ok
}

/** Sasha 232 · iPhone Safari: audio plays only from a tap, PER ELEMENT. Her replies were each a NEW Audio(), played after the TTS
 *  fetch (outside any tap) → refused (NotAllowedError) and dropped — silent, while the toggle said "Voice on". 230's unlock()
 *  played an empty `new Audio()`, which unlocks nothing. Now: ONE element for all her speech, primed with this silent clip
 *  INSIDE the tap (synchronously), then reused — iOS lets an element that a tap has played play again. A refusal is shown. */
const SILENT = 'data:audio/wav;base64,UklGRkQDAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YSADAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA=='

function useSpeaker() {
  const q = useRef<string[]>([])
  const playing = useRef(false)
  const on = useRef(false)
  const muted = useRef(false)
  const el = useRef<HTMLAudioElement | null>(null)
  const primed = useRef(false)
  const route = useRef<((t: string) => Promise<void>) | null>(null)   // Sasha 225 · her face, while it's up
  const subs = useRef(new Set<(b: boolean) => void>())
  const blockSubs = useRef(new Set<(b: boolean) => void>())
  const lastBlocked = useRef<string | null>(null)
  const epoch = useRef(0)   // Sasha 233 · bumped by interrupt(): a line fetched before it is never played
  const asleep = useRef(false)   // Sasha 246 item 2 · asleep: nothing is said aloud
  const emit = (b: boolean) => subs.current.forEach(f => f(b))
  const setBlocked = (t: string | null) => { lastBlocked.current = t; blockSubs.current.forEach(f => f(!!t)) }
  const audio = () => {
    if (!el.current) { el.current = new Audio(); el.current.setAttribute('playsinline', ''); el.current.preload = 'auto' }
    return el.current
  }
  const mp3 = async (text: string): Promise<'played' | 'blocked' | 'failed'> => {
    const mine = epoch.current
    try {
      const r = await fetch(apiUrl('/api/voice/tts'), { method: 'POST', headers: apiHeaders(), body: JSON.stringify({ text }) })   // Sasha 225 · ONE content-type (two were merged → 422: /s2 was silent)
      if (!r.ok) return 'failed'
      if (mine !== epoch.current) return 'played'   // interrupted while it was being fetched
      const a = audio()
      const url = URL.createObjectURL(await r.blob())
      a.src = url
      const got = await new Promise<'played' | 'blocked' | 'failed'>(res => { a.onended = () => res('played'); a.onpause = () => res('played'); a.onerror = () => res('failed'); a.play().catch(e => res(e?.name === 'NotAllowedError' ? 'blocked' : 'failed')) })   // Sasha 233 · paused (interrupted) ends it too
      URL.revokeObjectURL(url)
      if (got === 'blocked') setBlocked(text); else if (got === 'played') setBlocked(null)
      return got
    } catch { return 'failed' }   // her words are on screen either way
  }
  const next = useCallback(async () => {   // one at a time, in order, until the queue is empty
    if (playing.current) return
    playing.current = true
    while (q.current.length) {
      emit(true)
      const text = q.current.shift() as string
      if (route.current) await route.current(text).catch(() => {})
      else await mp3(text)
      emit(false)
    }
    playing.current = false
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refs only
  }, [])
  return useMemo(() => ({
    /** Call SYNCHRONOUSLY inside a tap / key / submit handler: primes the one element iOS will then let her speak through. */
    unlock: () => {
      on.current = true
      holdPlayAndRecord('her voice')   // Sasha 267 · ONE audio session: "playback" here made iOS refuse the mic (lib/audio-session)
      if (primed.current || playing.current) return
      try { const a = audio(); a.src = SILENT; a.play().then(() => { primed.current = true }).catch(() => {}) } catch { /* no audio */ }
    },
    say: (t: string) => { if (on.current && !muted.current && !asleep.current && t.trim()) { q.current.push(t); next() } },
    sayNow: async (t: string) => { emit(true); const r = muted.current || asleep.current ? 'played' as const : await mp3(t); if (r === 'played') on.current = true; emit(false); return r },
    setRoute: (fn: ((t: string) => Promise<void>) | null) => { route.current = fn },
    setMuted: (m: boolean) => { muted.current = m; if (m) { q.current = []; setBlocked(null) } },
    /** Sasha 233 · "Thanks!" mid read-back: what she's saying stops now, and nothing queued is said. */
    interrupt: () => { epoch.current++; q.current = []; try { if (el.current && !el.current.paused) el.current.pause() } catch { /* nothing playing */ } },
    onSpeaking: (fn: (b: boolean) => void) => { subs.current.add(fn); return () => { subs.current.delete(fn) } },
    /** Sasha 232 · a reply the phone refused to play: the toggle says so (never "Voice on" while she's silent); a tap replays it. */
    onBlocked: (fn: (b: boolean) => void) => { blockSubs.current.add(fn); return () => { blockSubs.current.delete(fn) } },
    replayBlocked: () => { const t = lastBlocked.current; setBlocked(null); if (t && !muted.current && !asleep.current) { q.current.unshift(t); next() } },
    /** Sasha 246 item 2 · asleep: what she's saying stops mid-word (as interrupt) and nothing is said until she wakes. */
    setAsleep: (a: boolean) => {
      asleep.current = a
      if (a) { epoch.current++; q.current = []; setBlocked(null); try { if (el.current && !el.current.paused) el.current.pause() } catch { /* nothing playing */ } }
    },
    isOn: () => on.current,
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refs and a stable callback: one speaker for the page's life
  }), [])
}

// Sasha 226 · each one something she does. Sasha 249 · ONE CAPABILITY LIST: generated from backend/agapi/s2_home.py CAPABILITIES
// (frontend/lib/capabilities.generated.mjs) — the same chips as /next
/** Sasha 225 · one honest line after an action: what she can do next (each is a real tool on /s2). */
const AFTER: Partial<Record<string, string>> = {
  booked: 'If you’re running late, just tell me — or I can email the details to someone, or put it in your calendar.',
  calendar: 'It’s in your Activity too, with its proof.',
  pay: 'I’ll tell you here the moment it’s confirmed.',
  sent: 'It’s in your Activity, with its proof.',
}

function VenueCards({ cards, choose }: { cards: Extract<Card, { k: 'venues' }>['cards']; choose: (name: string, placeId: string) => void }) {
  // Sasha 248 · ONE PLACE CARD (components/cards/PlaceCard): the same card and detail sheet as /next — a tap on the photo opens it
  return (
    <div style={{ display: 'flex', gap: 10, overflowX: 'auto', maxWidth: '100%', padding: '4px 2px 8px', scrollSnapType: 'x mandatory' }}>
      {cards.map(c => <PlaceCard key={c.place_id} card={c} onBook={choose} />)}
    </div>
  )
}



/** Sasha 226 · a file as base64, unchanged (a CSV or a PDF goes as it is). */
function asBase64(file: File): Promise<string> {
  return new Promise((res, rej) => {
    const fr = new FileReader()
    fr.onload = () => res(String(fr.result).split(',')[1] ?? '')
    fr.onerror = () => rej(fr.error)
    fr.readAsDataURL(file)
  })
}
const UPLOAD_MAX = 5 * 1024 * 1024   // the backend's own cap (agapi s2_subscriptions / s2_fine_print MAX_BYTES: 5 MB)

/** Sasha 226 · the paperclip: a bank statement (→ statement_ref for find_subscriptions) or a card (→ card_image_ref for add_card).
 *  The file goes through /api/s2-upload/* to the backend's memory (never on disk); on success the ref is said in the chat so she
 *  passes it to her tool; on failure the server's own words are her line — never a fake "got it". */
function Clip({ busy, send, say }: { busy: boolean; send: (t: string) => void; say: (t: string) => void }) {
  const [open, setOpen] = useState(false)
  const [working, setWorking] = useState(false)
  const stmt = useRef<HTMLInputElement | null>(null)
  const card = useRef<HTMLInputElement | null>(null)
  async function picked(what: 'statement' | 'card', f?: File | null) {
    if (stmt.current) stmt.current.value = ''
    if (card.current) card.current.value = ''
    if (!f) return
    setWorking(true)
    try {
      const isImage = f.type.startsWith('image/')
      const isPdf = f.type === 'application/pdf' || /\.pdf$/i.test(f.name)
      const isCsv = /\.csv$/i.test(f.name) || f.type === 'text/csv'
      if (what === 'card' && !isImage) { say('A card is added from a photo or a screenshot — that file isn’t an image.'); return }
      if (what === 'statement' && !isImage && !isPdf && !isCsv) { say('A statement is a CSV, a PDF or a photo — that file isn’t one of those.'); return }
      let content: string, media: string
      if (isImage) { content = await shrink(f); media = 'image/jpeg' }
      else {
        if (f.size > UPLOAD_MAX) { say('That file is too large — 5 MB at most.'); return }
        content = await asBase64(f); media = isPdf ? 'application/pdf' : 'text/csv'
      }
      if (!content || (content.length * 3) / 4 > UPLOAD_MAX) { say(content ? 'That file is too large — 5 MB at most.' : 'That file couldn’t be read.'); return }
      const r = await fetch(what === 'statement' ? '/api/s2-upload/statement' : '/api/s2-upload/card-image', {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ media_type: media, content_base64: content }) })
      if (r.status === 401) { window.location.href = '/sign-in?next=/s2'; return }
      const j = await r.json().catch(() => ({}))
      const ref = what === 'statement' ? j?.statement_ref : j?.card_image_ref
      if (r.ok && j?.ok && typeof ref === 'string' && ref) {
        send(what === 'statement' ? `Here's my statement (statement_ref: ${ref}).` : `Add this card (card_image_ref: ${ref}).`)
      } else say(untag(String(j?.message || (what === 'statement' ? 'That statement couldn’t be uploaded.' : 'That card couldn’t be uploaded.'))))
    } catch { say('That file couldn’t be uploaded — try again?') }
    finally { setWorking(false) }
  }
  const item = { display: 'block', width: '100%', textAlign: 'left', padding: '12px 14px', background: 'transparent', border: 0, color: '#fff', fontSize: 15 } as const
  return (
    <div style={{ position: 'relative', flex: 'none' }}>
      <input ref={stmt} type="file" accept=".csv,.pdf,image/*" hidden onChange={e => picked('statement', e.target.files?.[0])} aria-label="A bank statement" />
      <input ref={card} type="file" accept="image/*" hidden onChange={e => picked('card', e.target.files?.[0])} aria-label="A card (photo or Wallet screenshot)" />
      <button type="button" onClick={() => setOpen(o => !o)} disabled={busy || working} aria-label="Add a statement or a card" aria-expanded={open}
        style={{ width: 40, height: 40, borderRadius: '50%', border: `1px solid ${C.line}`, background: C.card, color: '#fff', fontSize: 18, opacity: busy || working ? 0.5 : 1 }}>
        {working ? '…' : '📎'}</button>
      {open && (
        <div role="menu" style={{ position: 'absolute', bottom: 48, left: 0, minWidth: 250, background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, overflow: 'hidden', boxShadow: '0 10px 30px rgba(0,0,0,.5)', zIndex: 20 }}>
          <button type="button" role="menuitem" style={item} onClick={() => { setOpen(false); stmt.current?.click() }}>A bank statement</button>
          <button type="button" role="menuitem" style={{ ...item, borderTop: `1px solid ${C.line}` }} onClick={() => { setOpen(false); card.current?.click() }}>A card (photo or Wallet screenshot)</button>
        </div>)}
    </div>
  )
}



function After({ k }: { k: string }) {
  const line = AFTER[k]
  return line ? <div style={{ fontSize: 13.5, color: C.dim, margin: '6px 4px 0' }}>{line}</div> : null
}



/** Sasha 265 · item 4 (CR 99): THE ONE QUESTION IS THE CARD — "Fill in their page" / "Call them" (or one "OK"). The tap goes to the server
 *  with the card's read_back_id: there it IS the approval (approvals.in_app_tap), no model between. One tap: the buttons go. */
function CallCard({ c, tap }: { c: Extract<Card, { k: 'read_back' }>; tap: (title: string, readBackId: string, route: string) => void }) {
  const [tapped, setTapped] = useState<string | null>(null)
  return (
    <Box k="Your booking · one tap" h={untag(c.ask || '')}>
      {c.lines.filter(l => !/^\s*⚠/.test(l)).map((l, i) => <div key={i} style={{ fontSize: 14.5, padding: '2px 0', color: 'rgba(255,255,255,.88)' }}>{untag(l)}</div>)}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
        {(c.choices || []).map(o => (
          <button key={o.route} type="button" disabled={!!tapped} data-card-choice={o.route}
            onClick={() => { setTapped(o.route); tap(o.title, c.read_back_id || '', o.route) }}
            style={{ padding: '10px 18px', borderRadius: 999, border: o.route === 'call' ? 0 : `1px solid ${C.gold}`, background: o.route === 'call' ? C.gold : 'transparent',
              color: o.route === 'call' ? '#111' : C.gold, fontWeight: 700, opacity: tapped && tapped !== o.route ? 0.4 : 1 }}>{o.title}</button>))}
      </div>
    </Box>)
}

/** Sasha 269 · CR 100 · after a call nobody picked up: AgAPI's ONE question with its two choices ("Try once more" → the same booking's
 *  call, no new card · "Fill in their form" → their page), or — the second time — their page alone. Labels and words: the engine's. */
function NoAnswerCard({ c, tap }: { c: Extract<Card, { k: 'no_answer' }>; tap: (title: string, actId: string, route: string) => void }) {
  const [tapped, setTapped] = useState(false)
  const pill = (gold: boolean) => ({ padding: '10px 18px', borderRadius: 999, border: gold ? 0 : `1px solid ${C.gold}`, background: gold ? C.gold : 'transparent',
    color: gold ? '#111' : C.gold, fontWeight: 700, textDecoration: 'none', display: 'inline-block' })
  return (
    <Box k="No answer" h={untag(c.ask || '')}>
      <div data-no-answer={c.act_id} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
        {c.choices.map(o => o.id === 'call_again'
          ? <button key={o.id} type="button" disabled={tapped} data-card-choice="call_again" style={{ ...pill(true), opacity: tapped ? 0.4 : 1 }}
              onClick={() => { setTapped(true); tap(o.label, c.act_id, 'call_again') }}>{o.label}</button>
          : (o.page || c.page) ? <a key={o.id} href={o.page || c.page} target="_blank" rel="noopener noreferrer" data-card-choice="their_page" style={pill(false)}>{o.label}</a> : null)}
        {!c.choices.length && c.page ? <a href={c.page} target="_blank" rel="noopener noreferrer" data-card-choice="their_page" style={pill(false)}>{untag(c.page)}</a> : null}
      </div>
    </Box>)
}

function CardView({ c, choose, pick, send, tap }: { c: Card; choose: (t: string) => void; pick: (name: string, placeId: string) => void; send: (t: string) => void
  tap: (title: string, readBackId: string, route: string) => void }) {
  if (c.k === 'read_back' && c.choices && c.choices.length && c.read_back_id) return <CallCard c={c} tap={tap} />
  if (c.k === 'no_answer') return <NoAnswerCard c={c} tap={tap} />
  if (c.k === 'sign_in') return (   /* Sasha 274 · rows 1063/1064 — the same sign-in as the header's, this conversation carried */
    <Box k="Booking as a guest" h="Sign in to book for real — this conversation comes with you">
      <button type="button" data-sign-in-card onClick={() => window.dispatchEvent(new Event('s2-sign-in'))}
        style={{ marginTop: 6, padding: '10px 18px', borderRadius: 999, border: 0, background: C.gold, color: '#111', fontWeight: 700 }}>Sign in</button>
    </Box>)
  if (c.k === 'counter_card') return <CounterCard card={c.card} />
  if (c.k === 'my_cards') return <MyCards cards={c.cards} choose={choose} />
  if (c.k === 'accident') return <AccidentCard view={c.view} send={send} />
  if (c.k === 'claim_status') return <ClaimStatus claim={c.claim} />
  if (c.k === 'prepared') return <PreparedCard ev={c.ev} />
  if (c.k === 'subscriptions') return <SubscriptionsCard items={c.items} total={c.total} source={c.source} send={send} />
  // Sasha 252 · things to do are places: the ONE place card and sheet (ActivityCard retired — EU 251 FAIL 5)
  if (c.k === 'activities') return (<><VenueCards cards={c.cards as never} choose={pick} />
    {c.unread.length ? <div style={{ fontSize: 13, color: C.dim, margin: '4px 2px' }}>Couldn&apos;t check on their official sites: {c.unread.map(untag).join(', ')}</div> : null}</>)
  if (c.k === 'keep_capture') return <KeepCapture what={c.what} />
  if (c.k === 'wa_open') return <WaOpen c={c} />
  if (c.k === 'handover') return (   // Sasha 236 · as /next's onHandover: our Tap to finish in a sheet over her; a platform's page in their browser
    <Box k="One tap left" h="Finish it on their page">
      <button type="button" onClick={() => { if (c.external) window.open(c.url, '_blank', 'noopener'); else window.dispatchEvent(new CustomEvent('s2-handover', { detail: c.url })) }}
        style={{ marginTop: 6, padding: '10px 18px', borderRadius: 999, border: 0, background: C.gold, color: '#111', fontWeight: 700 }}>Tap to finish</button>
    </Box>)
  if (c.k === 'trip') return (
    <Box k="Your trip" h={c.what}>
      <button type="button" onClick={() => window.dispatchEvent(new Event('s2-open-trip'))}
        style={{ marginTop: 6, padding: '8px 14px', borderRadius: 999, border: `1px solid ${C.gold}`, background: 'transparent', color: C.gold, fontWeight: 600 }}>See the whole trip</button>
    </Box>)
  if (c.k === 'plans') return <Plans items={c.items} on={c.on} />
  if (c.k === 'notice') return (
    <Box k={c.status ? untag(c.status) : 'Update'} h={untag(c.title)}>
      {c.lines.map((l, i) => <div key={i} style={{ fontSize: 14.5, padding: '2px 0', color: 'rgba(255,255,255,.88)' }}>{untag(l)}</div>)}
    </Box>)
  if (c.k === 'capabilities') return (
    <Box k="What I can do">
      {c.groups.map(g => (
        <div key={g.group} style={{ marginTop: 8 }}>
          <div style={{ fontWeight: 700, color: C.gold, fontSize: 14 }}>{g.group}</div>
          {g.items.map(i => <div key={i} style={{ fontSize: 14.5, padding: '2px 0', color: 'rgba(255,255,255,.88)' }}>{i}</div>)}
        </div>))}
    </Box>)
  if (c.k === 'venues') return <VenueCards cards={c.cards} choose={pick} />   // Sasha 231 · the tap carries the card's place_id
  if (c.k === 'booked') return <><Box k={/^Partly booked/i.test(c.line) ? 'Partly booked' : 'Booked'} h={firstSentences(untag(c.line.replace(/^✅\s*/, '').replace(/^(Partly )?Booked:\s*/i, '')), 2)} tone="rgba(126,226,168,.5)" /><After k="booked" /></>
  if (c.k === 'calendar') return (
    <><Box k="Add to your calendar" h={untag(c.title || 'Your booking')}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {(['google', 'outlook', 'apple'] as const).filter(x => c.links[x]).map(x => (
          <a key={x} href={c.links[x]} target="_blank" rel="noreferrer" style={{ padding: '8px 14px', borderRadius: 999, border: `1px solid ${C.gold}`, color: C.gold, fontWeight: 600, textDecoration: 'none' }}>
            {x === 'google' ? 'Google' : x === 'outlook' ? 'Outlook' : 'Apple / other'}</a>))}
      </div>
    </Box><After k="calendar" /></>)
  if (c.k === 'pay') return <><div style={{ background: C.card, border: `1px solid ${C.gold}`, borderRadius: 16, padding: 14, marginTop: 8 }}><PayHere clientSecret={c.client_secret} url={c.url} totalEur={c.total_eur} alreadyPaid={c.already_paid} /></div>{!c.already_paid && <After k="pay" />}</>
  const ACT_HEAD: Record<string, string> = { late: 'Ready to call · on your yes', change: 'Ready to change · on your yes', cancel: 'Ready to cancel · on your yes' }   // Sasha 226
  const head = c.act && ACT_HEAD[c.act] ? ACT_HEAD[c.act] : c.what ? (c.status === 'sent' ? 'Sent' : c.status === 'not_sent' ? 'Not sent' : 'Ready to send · on your yes')
    : (c.total ? `Ready to book · €${Math.round(c.total).toLocaleString()} all in` : 'Ready to book · on your yes')
  return (
    <><Box k={head} h={c.what === 'email' ? (c.live ? "From Sasha's own address" : 'Kept here · not sent') : c.what === 'whatsapp' ? "From Sasha's own number" : undefined}>
      {c.lines.filter(l => !/^\s*⚠/.test(l)).map((l, i) => <div key={i} style={{ fontSize: 14.5, padding: '2px 0', color: 'rgba(255,255,255,.88)' }}>{untag(l)}</div>)}
    </Box>{c.what && c.status === 'sent' ? <After k="sent" /> : null}</>)
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
  const [tab, setTab] = useState<'sasha' | 'activity' | 'keep' | 'trip'>('sasha')   // Sasha 235 · 'keep': My Keep · 236 · 'trip': the trip board
  const [handover, setHandover] = useState<string | null>(null)   // Sasha 236 · Tap to finish, in a sheet over her
  useEffect(() => {
    const h = (e: Event) => setHandover(String((e as CustomEvent).detail || '') || null)
    const t = () => setTab('trip')
    window.addEventListener('s2-handover', h); window.addEventListener('s2-open-trip', t)
    return () => { window.removeEventListener('s2-handover', h); window.removeEventListener('s2-open-trip', t) }
  }, [])
  const [openDays, setOpenDays] = useState<Set<number>>(new Set([1]))
  const [msgs, setMsgs] = useState<Msg[]>([])
  const msgsRef = useRef<Msg[]>([])   // Sasha 274 · rule 4 reads what is on the screen (mid-booking)
  useEffect(() => { msgsRef.current = msgs }, [msgs])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const queued = useRef<string[]>([])   // Sasha 257 · messages sent while she was answering: sent next, in order
  const session = useRef('')
  useEffect(() => { session.current = `s2-${Date.now().toString(36)}-${crypto.randomUUID().slice(0, 8)}` }, [])
  const speaker = useSpeaker()
  const end = useRef<HTMLDivElement>(null)
  const typeBox = useRef<HTMLInputElement | null>(null)
  const [name, setName] = useState<string | null | undefined>(undefined)   // undefined: not known yet (the hello waits ≤ 0.9 s)
  const [muted, setMuted] = useState(false)
  const [voiceBlocked, setVoiceBlocked] = useState(false)   // Sasha 232 · the phone refused to play her — the toggle says so
  useEffect(() => speaker.onBlocked(setVoiceBlocked), [speaker])
  // Sasha 264 · item 7: the mic's gate has an owner here — her own voice closes it and her silence opens it (it had none: an
  // auto-started mic stayed gated, deaf, while it showed connected)
  const micGate = useRef<((v: boolean) => void) | null>(null)
  useEffect(() => speaker.onSpeaking(b => micGate.current?.(b)), [speaker])
  useEffect(() => {   // Sasha 230 · the voice toggle is remembered (this browser): read once, applied to her voice
    let m = false
    try { m = localStorage.getItem('s2_muted') === '1' } catch { /* private mode: voice on */ }
    if (m) { speaker.setMuted(true); const t = setTimeout(() => setMuted(true), 0); return () => clearTimeout(t) }
  }, [speaker])
  const [chipAt, setChipAt] = useState(0)
  useEffect(() => {
    if (!signedIn) return
    const t = setTimeout(() => setName(n => (n === undefined ? null : n)), 900)
    fetch('/api/s2-me', { cache: 'no-store' }).then(r => r.json()).then(j => setName(j?.name || null)).catch(() => setName(null))
    return () => clearTimeout(t)
  }, [signedIn])
  useEffect(() => { const t = setInterval(() => setChipAt(i => (i + 1) % CHIPS.length), 4000); return () => clearInterval(t) }, [])
  const histRef = useRef<{ role: string; content: string }[]>([])
  // Sasha 231 · "thanks / bye" → she rests: faded, the mic off (not listening) until a tap; a tap brings her back, no re-introduction
  const [dormant, setDormant] = useState(false)
  const micUsed = useRef(false)
  const [woke, setWoke] = useState(false)
  // Sasha 246 item 2 · THE PAUSE / SLEEP BUTTON (lib/sleep-rule.mjs): asleep = silent, the mic off, her face dimmed.
  // She wakes on the button, a tap on her face, a press of the mic, or typing — and says "I'm here".
  const [asleep, setAsleep] = useState(false)
  const asleepRef = useRef(false)
  // Sasha 273 · items 3 + 4: the mic's REAL state (VoiceButton strict: hearing now), its two moves, the last activity, rule 4's answer
  const [micLive, setMicLive] = useState(false)
  const voiceCtl = useRef<VoiceCtl | null>(null)
  const lastAt = useRef<number | null>(null)
  const touch = useCallback(() => { const t = Date.now(); lastAt.current = t; try { localStorage.setItem(LAST_KEY, String(t)) } catch { /* private mode */ } }, [])
  const [arrive, setArrive] = useState<boolean | undefined>(undefined)
  // a reload while this browser's own last activity is recent: no arrival, from the first paint (never a one-tick full-size flip)
  const quick = useSyncExternalStore(noSub, () => { const l = localLastAt(); return l && !reappear({ lastAt: l, now: Date.now(), tz: tzNow() }).greet ? false : undefined }, () => undefined)
  const newsRef = useRef<string | null>(null)   // Sasha 273 · item 4 (c): news that came while they were away
  const [lead, setLead] = useState<string | null>(null)   // …and the arrival that leads with it
  const loadedAt = useRef(0)
  const comeBackRef = useRef<(() => void) | null>(null)   // Sasha 273 · the one return handler (below), for the events' replay
  const checkReleaseRef = useRef<(() => void) | null>(null)   // Sasha 274 · the release check (below), for a turn's end
  const sleepEvent = useCallback((ev: 'tap_pause' | 'tap_face' | 'press_mic' | 'typed') => {
    const r = sleepStep(asleepRef.current ? ASLEEP : AWAKE, ev)
    const nowAsleep = r.state === ASLEEP
    if (nowAsleep === asleepRef.current) return
    asleepRef.current = nowAsleep
    setAsleep(nowAsleep)
    try { sessionStorage.setItem('s2_paused', nowAsleep ? '1' : '0') } catch { /* private mode */ }   // Sasha 273 · paused stays paused, a reload too
    if (r.effects.stopAudio) speaker.setAsleep(true)   // mid-word: the element pauses, the queue empties (her face: S2Hello)
    if (nowAsleep) return
    speaker.setAsleep(false)
    speaker.unlock()   // inside the tap / key that woke her
    setDormant(false)
    if (r.effects.sayHere) setMsgs(ms => [...ms, { role: 'sasha', text: HERE, cards: [] }])   // shown only: never sent to her as history
    if (r.effects.speakHere) speaker.say(HERE)
  }, [speaker])
  // Sasha 231 · MEMORY ACROSS VISITS: what she remembers for this account (masked) — "Welcome back — we were looking at …"
  const [backLine, setBackLine] = useState<string | null | undefined>(undefined)
  const backLineRef = useRef<string | null | undefined>(undefined)
  useEffect(() => { backLineRef.current = backLine }, [backLine])
  /** Sasha 273 · item 4 · RULE 4 now (lib/presence-rule.mjs reappear): the last activity known, the news that came, paused or not. */
  // Sasha 274 · item 1: + mid-booking (her question waiting on screen — greeting-rule.mjs midFlow — or, at load, the record's pending)
  const rule4 = useCallback((mid?: boolean) => reappear({ lastAt: lastAt.current, now: Date.now(), tz: tzNow(), news: newsRef.current, asleep: asleepRef.current,
    midFlow: mid ?? midFlow(msgsRef.current) }), [])
  useEffect(() => {
    if (!signedIn) return
    let live = true
    loadedAt.current = Date.now()
    const carried = takeCarry()   // Sasha 274 · a reload for a new release: this tab's own conversation, exactly as it was
    if (carried) { histRef.current = carried.hist; setTimeout(() => setMsgs(ms => (ms.length ? ms : carried.msgs)), 0) }   // out of the effect's own pass
    const l = localLastAt()
    if (l) lastAt.current = l
    const t = setTimeout(() => { setBackLine(b => (b === undefined ? null : b)); setArrive(a => (a === undefined ? rule4().greet : a)) }, 2500)
    fetch(`/api/s2-memory?session=${encodeURIComponent(session.current)}`, { cache: 'no-store' }).then(r => r.json()).then((j: Ev) => {
      if (!live) return
      const line = typeof j?.line === 'string' && j.line ? untag(j.line) : null
      const server = typeof j?.last_at === 'string' ? Date.parse(j.last_at) : NaN   // Sasha 273 · the conversation's last turn, every device
      if (Number.isFinite(server) && server > (lastAt.current || 0)) lastAt.current = server
      // Sasha 273 · item 4 (the 11:03 bug, Tyler's screenshot): the opening line was appended on EVERY load — an iPhone reloading a
      // backgrounded tab mid-booking put "Hey Tyler, what can I help you with?" right after "Shall I call them now…?". Only rule 4 greets.
      const recent: { role: string; content: string; cards?: boolean }[] = (Array.isArray(j.recent) ? j.recent : [])
        .filter((m: Ev) => (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string' && m.content && m.content !== '[removed]')
      // Sasha 274 · mid-booking at load: the record says a question or a read-back waits, or her last restored line asks one
      const mid = !!(j?.pending && (j.pending.kind === 'question' || j.pending.kind === 'hold')) ||
        midFlow(recent.map(m => ({ role: m.role === 'user' ? 'user' : 'sasha', text: m.content })))
      const r = rule4(mid)
      const greet = r.greet && r.lead === 'hello'
      if (r.lead === 'news') { setLead(newsRef.current); newsRef.current = null }   // she leads with it (her arrival's first words)
      setArrive(a => (a === undefined ? r.greet : a))
      setBackLine(line)
      if (r.greet) touch()
      if (!line) return
      histRef.current = [...recent.map(m => ({ role: m.role, content: m.content })), ...(greet ? [{ role: 'assistant', content: line }] : [])]   // she carries on from where it stopped
      // Sasha 233 · her cards go back under the line that SHOWED them (marked by the server), never simply under the last line
      const marked = recent.map(m => !!m.cards).lastIndexOf(true)
      const from = Math.max(0, Math.min(recent.length - 8, marked >= 0 ? marked - 1 : recent.length))
      const cards = j.screen?.cards
      const shown: Msg[] = recent.slice(from).map(m => ({ role: m.role === 'user' ? 'user' as const : 'sasha' as const, text: untag(m.content), restored: true,
        cards: m.cards && Array.isArray(cards) && cards.length ? [{ k: 'venues' as const, cards: untagDeep(cards) }] : [] }))
      setMsgs(ms => (ms.length ? ms : carried ? carried.msgs : [...shown, ...(greet ? [{ role: 'sasha' as const, text: line, cards: [], restored: true }] : [])]))
      if (carried) histRef.current = carried.hist
    }).catch(() => { setBackLine(null); setArrive(a => (a === undefined ? rule4().greet : a)) })
    return () => { live = false; clearTimeout(t) }
  }, [signedIn, rule4, touch])
  useEffect(() => {   // Sasha 273 · paused stays paused — a reload of this tab too (the Pause is theirs, kept for the tab)
    let p = false
    try { p = sessionStorage.getItem('s2_paused') === '1' } catch { /* private mode */ }
    if (!p || asleepRef.current) return
    asleepRef.current = true; speaker.setAsleep(true)
    const t = setTimeout(() => setAsleep(true), 0)
    return () => clearTimeout(t)
  }, [speaker])

  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [msgs])
  useEffect(() => {   // a payment settled (Pacioli): said here, and the pay card turns to Paid
    if (!signedIn) return
    const es = new EventSource('/api/sasha-agent/events?since=0')
    es.onmessage = m => {
      let ev: Ev
      try { ev = untagDeep(JSON.parse(m.data)) } catch { return }
      // Sasha 273 · item 4 (c): NEWS — her line about something that happened after their last activity, heard while the page was
      // away (hidden) or replayed as it loads: rule 4's (c). Her return leads with it; a person here and talking just hears it.
      const said = String(ev.say || ev.text || '').trim()
      const at = Number(ev.at) > 0 ? Number(ev.at) * 1000 : Date.now()
      let held = false   // news kept for her return: her reappearance says it — once, never also here
      if (said && ['proactive', 'venue_notice', 'booked', 'booking_failed'].includes(String(ev.type)) && (!lastAt.current || at > lastAt.current)
          && (document.visibilityState === 'hidden' || Date.now() - loadedAt.current < 10000)) {
        newsRef.current = untag(said)
        held = true
        if (document.visibilityState !== 'hidden') setTimeout(() => comeBackRef.current?.(), 0)   // the load's own replay: rule 4 now
      }
      if (ev.type === 'proactive' && ev.say) {   // Sasha 227 · "day before pickup": her one line, and the counter card
        const card: Card[] = ev.render?.kind === 'counter_card' && ev.render.card ? [{ k: 'counter_card', card: ev.render.card }]
          : ev.render?.kind === 'subscriptions' && Array.isArray(ev.render.items)   // Sasha 260 · their receipts, read after the turn: the same card
            ? [{ k: 'subscriptions', items: ev.render.items, total: ev.render.total, source: ev.render.source }]
          : ev.render?.kind === 'no_answer' && ev.render.act_id   // Sasha 269 · a call nobody picked up: AgAPI's question, as a card
            ? [{ k: 'no_answer', act_id: String(ev.render.act_id), ask: ev.render.ask || undefined, page: ev.render.page || undefined,
                 choices: Array.isArray(ev.render.choices) ? ev.render.choices : [] }] : []
        setMsgs(ms => [...ms, { role: 'sasha', text: untag(String(ev.say)), cards: card }])
        if (!held) speaker.say(String(ev.say))
        return
      }
      if (ev.type === 'venue_notice') {   // Sasha 226 · the venue's answer to "I'm running late" / a change — in their words, when it comes
        const lines: string[] = Array.isArray(ev.lines) ? ev.lines.map(String) : [String(ev.say || '')]
        const title = `${ev.purpose === 'change' ? 'Change' : 'Running late'} · ${String(ev.venue || 'the venue')}`
        setMsgs(ms => [...ms, { role: 'sasha', text: '', cards: [{ k: 'notice', title, lines, status: ev.outcome === 'yes' ? 'Done' : ev.state === 'not_reached' ? 'No answer' : 'Their answer' }] }])
        if (!held) speaker.say(String(ev.say || ''))
        return
      }
      if (ev.type !== 'booked' && ev.type !== 'booking_failed') return
      const line = ev.type === 'booked' ? bookedLine(ev) : null   // Sasha 249 · the card from the `booked` event, the server's one status
      setMsgs(ms => [...ms.map(x => ({ ...x, cards: x.cards.map(c => (c.k === 'pay' ? { ...c, already_paid: ev.type === 'booked' } : c)) })),
                     { role: 'sasha', text: String(ev.say || ev.text || ''), cards: line ? [{ k: 'booked', line }] : [] }])
    }
    return () => es.close()
  }, [signedIn, speaker])

  const send = useCallback(async (text: string, pick?: { place_id: string }, tap?: { read_back_id?: string; act_id?: string; choice: string }) => {
    const t = text.trim()
    if (!t) return
    // Sasha 257 · Jon (row 861): "she can't hear me or just doesn't respond — tried 5 times". One turn reached her; the rest were
    // DROPPED here while a reply was still open (busy). A message sent while she's answering is kept and sent next — never lost.
    if (busy) { queued.current = [...queued.current, t]; setInput(''); return }
    if (dormant) setDormant(false)   // Sasha 231 · a message wakes her, with no re-introduction
    if (asleepRef.current) sleepEvent('typed')   // Sasha 246 item 2 · a message wakes her
    setBusy(true)
    touch()   // Sasha 273 · activity: their turn (typed, spoken, a chip or a card's tap)
    setInput('')
    setMsgs(ms => [...ms, { role: 'user', text: t, cards: [] }, { role: 'sasha', text: '', cards: [] }])
    const patch = (f: (m: Msg) => Msg) => setMsgs(ms => { const c = ms.slice(); c[c.length - 1] = f(c[c.length - 1]); return c })
    // Sasha 265 · item 5: a request for work hears voice.first_line the instant it's sent (the network took 0.8–1.4 s)
    // Sasha 268 · item 4: his FIRST REAL REQUEST while she is full size (voice.py's work rule, or a card's pick or tap — each starts
    // work; small talk never) → her line by code (voice.CAMERA_OFF), said by her (bye), then the corner circle and the work
    const isRequest = !!(pick || tap || isWork(t))
    const leaving = isRequest && !!helloCtl.current?.big()
    const said1 = leaving ? (cameraOffLine() || null) : pick || tap ? null : takeFirstLine(t)   // Sasha 273 · item 8: once per request, then the quiver
    if (leaving) {
      if (said1) patch(m => ({ ...m, hold: said1 }))
      byeUntil.current = Date.now() + 9000   // her line first: the stream's lines are shown, not spoken over it
      void helloCtl.current?.bye(said1 || '', !muted)
    } else if (said1) { patch(m => ({ ...m, hold: said1 })); speaker.say(said1) }
    let reply = ''
    // Sasha 257 · a reply stream that goes quiet (a phone's network, a connection held open) never leaves the page "busy" — the
    // mic stays off and every message is refused while it is. STALL_MS of silence → it's stopped and said; `done` ends it.
    const abort = new AbortController()
    let stall: ReturnType<typeof setTimeout> | undefined
    const arm = () => { if (stall) clearTimeout(stall); stall = setTimeout(() => abort.abort(), STALL_MS) }
    try {
      arm()
      const r = await fetch('/api/s2-agent', { method: 'POST', headers: { 'content-type': 'application/json' }, signal: abort.signal,
        body: JSON.stringify({ message: t, history: histRef.current.slice(-30), session_id: session.current, ...(pick ? { pick } : {}), ...(tap ? { tap } : {}), ...(said1 && !leaving ? { said_first: said1 } : {}) }) })   // Sasha 265 · the card's tap
      if (r.status === 401) { window.location.href = '/sign-in?next=/s2'; return }
      const rd = r.body?.getReader()
      const dec = new TextDecoder()
      let buf = '', finished = false
      while (rd && !finished) {
        arm()
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
          else if (ev.type === 'say') { if (ev.interrupt) speaker.interrupt(); speaker.say(ev.text) }
          else if (ev.type === 'tool_start' && helloCtl.current?.big()) {   // Sasha 268 · a request the rule missed: the first tool it starts
            const l = cameraOffLine(); if (l) patch(m => ({ ...m, hold: l })); byeUntil.current = Date.now() + 9000; void helloCtl.current.bye(l, !muted) }
          else if (ev.type === 'hold') { if (ev.first && said1) continue; patch(m => ({ ...m, hold: ev.text })); if (Date.now() > byeUntil.current) speaker.say(ev.say || ev.text) }   // 265 · never twice   // Sasha 257 · the holding line (row 863)
          else if (ev.type === 'replace') { reply = ev.text; patch(m => ({ ...m, text: untag(reply) })); if (ev.speak && ev.say) speaker.say(ev.say) }
          else if (ev.type === 'error') { reply = ev.message; patch(m => ({ ...m, text: untag(reply) })); speaker.say(ev.message) }
          // Sasha 249 · ONE STATUS: the "Booked" card was made here by a regex on her reply (/^✅ Booked/) — deleted. It comes only
          // from the `booked` event, its line from the server's one status (agapi/s2_status.py — get_status's own)
          else if (ev.type === 'done') { reply = ev.text || reply; if (ev.dormant) setDormant(true); patch(m => ({ ...m, text: untag(reply) })); finished = true; rd.cancel().catch(() => {}) }
          else if (ev.type === 'booked') { const line = bookedLine(ev); if (line) patch(m => ({ ...m, cards: [...m.cards.filter(x => x.k !== 'booked'), { k: 'booked', line }] })) }
          else if (ev.type === 'render') {
            const add0 = (c: Card) => patch(m => ({ ...m, cards: [...m.cards.filter(x => x.k !== c.k), c] }))
            // Sasha 274 · rows 1063/1064: a booking tried as a GUEST offers sign-in, in the conversation, under its card
            const add = (c: Card) => { add0(c); if (ACTING === 'guest' && ['read_back', 'prepared', 'wa_open', 'handover', 'pay'].includes(c.k)) add0({ k: 'sign_in' }) }
            if (ev.kind === 'venues' && ev.preset) { const cs = shownCards(ev.preset); if (cs.length) add({ k: 'venues', cards: cs }) }
            else if (ev.kind === 'read_back' && Array.isArray(ev.read_back)) add({ k: 'read_back', lines: ev.read_back, what: ev.what, live: ev.live, status: ev.status, total: ev.total_eur, act: ev.act,
              ...(Array.isArray(ev.choices) && ev.choices.length && ev.read_back_id ? { ask: String(ev.ask || ''), choices: ev.choices, read_back_id: String(ev.read_back_id) } : {}) })
            else if (ev.kind === 'calendar' && ev.links) add({ k: 'calendar', title: ev.title, links: ev.links })
            else if (ev.kind === 'keep_capture') add({ k: 'keep_capture', what: ev.what === 'loyalty' ? 'loyalty' : 'passport' })
            else if (ev.kind === 'wa_open' && typeof ev.open === 'string' && ev.open.startsWith('https://wa.me/')) add({ k: 'wa_open', to: ev.to || {}, text: String(ev.text || ''), open: ev.open, why: String(ev.why || '') })   // Sasha 230
            else if (ev.kind === 'capabilities' && Array.isArray(ev.groups)) add({ k: 'capabilities', groups: ev.groups })
            else if (ev.kind === 'plans' && Array.isArray(ev.items)) add({ k: 'plans', items: ev.items, on: ev.on })
            else if (ev.kind === 'notice' && ev.title) add({ k: 'notice', title: String(ev.title), lines: Array.isArray(ev.lines) ? ev.lines : [], status: ev.status })
            else if (ev.kind === 'pay_here') add({ k: 'pay', client_secret: ev.client_secret, url: ev.url, total_eur: ev.total_eur, already_paid: ev.already_paid })
            else if (ev.kind === 'counter_card' && ev.card) add({ k: 'counter_card', card: ev.card })   // CR 75 · fine print
            else if (ev.kind === 'my_cards') add({ k: 'my_cards', cards: ev.cards || [] })
            else if (ev.kind === 'accident' && ev.view) add({ k: 'accident', view: ev.view })
            else if (ev.kind === 'claim_status' && ev.claim) add({ k: 'claim_status', claim: ev.claim })
            else if (ev.kind === 'handover' && typeof ev.url === 'string' && ev.url.startsWith('https://')) add({ k: 'handover', url: ev.url, external: !!ev.external })   // Sasha 236
            else if (['flights', 'stays', 'flight_chosen', 'total', 'trip', 'trip_changed'].includes(String(ev.kind))) {   // Sasha 236 · the trip board refreshes; one card says so
              window.dispatchEvent(new Event('sasha-plan-refresh'))
              const what = ev.kind === 'flights' ? 'Flights to choose from' : ev.kind === 'stays' ? 'Places to stay' : ev.kind === 'total' ? 'The total, all in' : 'Your trip, updated'
              add({ k: 'trip', what })
            }
            else if (ev.kind === 'prepared' && typeof ev.url === 'string') add({ k: 'prepared', ev })   // Sasha 248
            else if (ev.kind === 'subscriptions' && Array.isArray(ev.items)) add({ k: 'subscriptions', items: ev.items, total: ev.total, source: ev.source })   // CR 84
            else if (ev.kind === 'activities' && Array.isArray(ev.cards)) add({ k: 'activities', cards: ev.cards, unread: Array.isArray(ev.unread) ? ev.unread : [], date: ev.date })   // CR 81
          }
        }
      }
    } catch {
      patch(m => ({ ...m, text: m.text || 'I lost the connection there — say it once more?' }))
    } finally {
      if (stall) clearTimeout(stall)
      histRef.current = [...histRef.current, { role: 'user', content: t }, { role: 'assistant', content: reply }]
      touch()   // Sasha 273 · activity: her answer
      setBusy(false)
      busyRef.current = false
      setTimeout(() => checkReleaseRef.current?.(), 0)   // Sasha 274 · a turn ended: a new release? (reloads only at a safe moment)
    }
  }, [busy, speaker, dormant, sleepEvent, muted, touch])
  useEffect(() => {   // Sasha 257 · what they said while she was answering goes next, in order (never dropped)
    if (busy || asleep || !queued.current.length) return   // Sasha 268 · paused: it waits for Wake — a message typed BEFORE the pause never undoes it
    const [nxt, ...rest] = queued.current
    queued.current = rest
    void send(nxt)
  }, [busy, asleep, send])

  // Sasha 265 · item 3 · NEW CHAT: the conversation goes from the screen AND from her short-term memory, in its one place (the
  // conversation record, DELETE /api/s2-memory → s2_memory.clear_conversation — the same clear as /next). Bookings, trips and
  // receipts stay (the trip record). Only once the record says it's cleared is the screen cleared; if not, she says so.
  useEffect(() => { void loadFirstLine() }, [])
  useEffect(() => { holdPlayAndRecord('the page') }, [])   // Sasha 267 · before her face or voice starts, before any mic request   // Sasha 265 · item 5: voice.first_line's words and rule, read once
  const [clearing, setClearing] = useState(false)
  const helloCtl = useRef<HelloCtl | null>(null)   // Sasha 268 · her arrival: big? and bye (the line, then the circle)
  const byeUntil = useRef(0)
  // Sasha 266 · row 943 (a): the mic's own words when it isn't hearing (blocked, can't hear you) — on the page, never only a tooltip
  const [micNote, setMicNote] = useState<string | null>(null)
  const newChat = useCallback(async () => {
    if (busy || clearing) return
    setClearing(true)
    speaker.interrupt()
    try {
      const r = await fetch('/api/s2-memory', { method: 'DELETE', cache: 'no-store' })
      const j = await r.json().catch(() => null)
      if (!r.ok || !j?.ok) throw new Error('not cleared')
      histRef.current = []
      queued.current = []
      forgetAcks()   // Sasha 273 · item 8: a new chat is a new request
      session.current = `s2-${Date.now().toString(36)}-${crypto.randomUUID().slice(0, 8)}`
      setInput('')
      setMsgs([])
    } catch {
      setMsgs(ms => [...ms, { role: 'sasha', text: NOT_CLEARED, cards: [] }])
    } finally {
      setClearing(false)
    }
  }, [busy, clearing, speaker])
  // Sasha 273 · items 3 + 4 · THE ONE RETURN HANDLER (the page back from another tab or app — visibilitychange, a restored page —
  // and the load's own replayed news). The mic: resume what was live, if the browser allows it without a tap (else "Tap to talk",
  // honestly). Her: rule 4 (lib/presence-rule.mjs reappear) — 30 min quiet, a new day, or news → she reappears ("Hey <name>…", or
  // her news first); a quick return mid-conversation → nothing, no greeting. Paused stays paused (rule 4 says so). Leaving the page
  // stops what she is saying — she never resumes mid-sentence.
  const tabRef = useRef(tab)
  useEffect(() => { tabRef.current = tab }, [tab])
  // Sasha 274 · item 1 · A NEW RELEASE: an open page kept running the old code after a deploy. It compares its own build with the one
  // live now (/api/version) when it comes back and when a turn ends — never on a timer — and reloads only at a SAFE moment: she isn't
  // answering or speaking, no booking question waits (midFlow), she isn't full size, nothing is queued. The conversation goes across
  // the reload with it (this tab's sessionStorage, read once) and rule 4 then sees a quick return: no greeting, no arrival.
  const stale = useRef(false)
  const busyRef = useRef(false)
  useEffect(() => { busyRef.current = busy }, [busy])
  const speakingRef = useRef(false)
  const safeReload = useCallback(() => {
    if (!stale.current || busyRef.current || speakingRef.current || queued.current.length || midFlow(msgsRef.current) || helloCtl.current?.big()) return
    putCarry(msgsRef.current, histRef.current)
    console.log('[s2] a new release — reloading at a safe moment')
    window.location.reload()
  }, [])
  const checkRelease = useCallback(() => {
    if (BUILD === 'dev') return
    fetch('/api/version', { cache: 'no-store' }).then(r => r.json()).then(j => {
      if (typeof j?.build === 'string' && j.build && j.build !== 'dev' && j.build !== BUILD) { stale.current = true; safeReload() }
    }).catch(() => { /* asked again at the next return or turn */ })
  }, [safeReload])
  useEffect(() => { checkReleaseRef.current = checkRelease }, [checkRelease])
  useEffect(() => {   // Sasha 274 · the conversation's sign-in card: the same carry and sign-in as the header's account control
    const go = () => { putCarry(msgsRef.current, histRef.current, SIGN_IN_CARRY); window.location.href = '/sign-in?next=%2Fs2' }
    window.addEventListener('s2-sign-in', go)
    return () => window.removeEventListener('s2-sign-in', go)
  }, [])
  useEffect(() => speaker.onSpeaking(b => { speakingRef.current = b; if (!b) setTimeout(() => safeReload(), 0) }), [speaker, safeReload])
  const comeBack = useCallback(() => {
    voiceCtl.current?.resume()
    checkRelease()
    if (arrive === undefined && Date.now() - loadedAt.current < 3000) return   // the load's own rule 4 hasn't answered yet: it will
    const r = rule4()
    if (!r.greet || tabRef.current !== 'sasha') return
    if (!helloCtl.current?.again(r.lead === 'news' ? newsRef.current : null)) return
    newsRef.current = null
    const line = backLineRef.current
    if (r.lead === 'hello' && line) {
      setMsgs(ms => [...ms, { role: 'sasha', text: line, cards: [] }])
      histRef.current = [...histRef.current, { role: 'assistant', content: line }]
    }
    touch()
  }, [arrive, rule4, touch, checkRelease])
  useEffect(() => { comeBackRef.current = comeBack }, [comeBack])
  useEffect(() => {
    if (!signedIn) return
    const vis = () => { if (document.visibilityState === 'hidden') speaker.interrupt(); else comeBackRef.current?.() }
    const shown = (e: PageTransitionEvent) => { if (e.persisted) comeBackRef.current?.() }
    document.addEventListener('visibilitychange', vis); window.addEventListener('pageshow', shown)
    return () => { document.removeEventListener('visibilitychange', vis); window.removeEventListener('pageshow', shown) }
  }, [signedIn, speaker])
  // Sasha 274 · item 4 (row 1062): a tap that starts a conversation (New chat, a chip) IS the user gesture a phone needs — the mic starts
  // inside it, synchronously, when its permission is already granted and she isn't paused or muted. Never a permission prompt from it.
  const listenOnTap = () => {
    if (asleepRef.current || muted || micLive || dormant) return
    if (voiceCtl.current?.granted()) { micUsed.current = true; voiceCtl.current.tap() }
  }
  const wake = () => { setDormant(false); setWoke(micUsed.current); speaker.unlock() }   // she was listening → listening again
  const hello = <S2Hello talker={speaker} name={name} signedIn={signedIn} backLine={backLine} dormant={dormant} asleep={asleep} onWake={() => sleepEvent('tap_face')}
    started={tab !== 'sasha'} ctlRef={helloCtl} arrive={arrive !== undefined ? arrive : quick} micLive={micLive} lead={lead} />   // Sasha 273 · rule 4's answer, the mic's truth, her news · Sasha 268 · small talk keeps her full size; his first real request (send) sends her to work   // Sasha 267 · another tab is him acting too: she goes to the circle (her frame sat over My Keep, swallowing taps)   // Sasha 265 · item 2: turns restored from last time don't end this arrival's opening · the same place in every branch: it outlives the sign-in check · Sasha 251 · started: their first turn ends the opening
  if (signedIn === null) return <><main style={{ minHeight: '100dvh', background: C.bg }} />{hello}</>
  if (!signedIn) return (<>
    <main style={{ minHeight: '100dvh', background: C.bg, color: '#fff', display: 'grid', placeItems: 'center', padding: 24, fontFamily: 'system-ui' }}>
      <div style={{ textAlign: 'center', maxWidth: 340 }}>
        <div style={{ fontSize: 34, fontWeight: 700, fontFamily: "'Playfair Display',Georgia,serif" }}>Sasha</div>
        <p style={{ color: C.dim, marginTop: 8 }}>Your personal concierge. Sign in with your email — a 6-digit code, right here.</p>
        <a href="/sign-in?next=/s2" style={{ display: 'inline-block', marginTop: 18, padding: '12px 22px', borderRadius: 999, background: C.gold, color: '#111', fontWeight: 700, textDecoration: 'none' }}>Sign in</a>
      </div>
    </main>{hello}</>)

  return (<>
    {/* Sasha 273 · item 5 (Tyler's iPhone, Safari 26: the bottom address pill sat on "Voice on" and "New chat"): the shell IS the dynamic
        viewport (height 100dvh) — the conversation scrolls inside it, the controls never leave it, and the bottom keeps the safe area */}
    <main data-s2-shell style={{ height: '100dvh', background: C.bg, color: '#fff', display: 'flex', flexDirection: 'column', fontFamily: 'system-ui', maxWidth: 560, width: '100%', margin: '0 auto', overflow: 'hidden', opacity: dormant ? 0.22 : 1, filter: dormant ? 'saturate(.4)' : 'none', transition: 'opacity 1.2s ease, filter 1.2s ease' }}>
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '14px 16px', paddingTop: 'max(18px, calc(env(safe-area-inset-top) + 10px))' }}>
        {/* Sasha 257 · Tyler (row 860): who is signed in, said quietly here (whoami) — the floating pill over the chat is gone */}
        <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "'Playfair Display',Georgia,serif" }}>Sasha</div>
        <nav style={{ display: 'flex', gap: 6 }}>
          {(['sasha', 'trip', 'activity', 'keep'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ padding: '7px 14px', borderRadius: 999, border: `1px solid ${tab === t ? C.gold : C.line}`, background: 'transparent', color: tab === t ? C.gold : C.dim, fontWeight: 600 }}>
              {t === 'sasha' ? 'Sasha' : t === 'keep' ? 'My Keep' : t === 'trip' ? 'Trip' : 'Activity'}</button>))}
        </nav>
      </header>
      <AccountControl style={{ padding: '0 16px 8px', textAlign: 'right' }} onSignIn={() => putCarry(msgsRef.current, histRef.current, SIGN_IN_CARRY)} />{/* Sasha 274 · rows 1063/1064 */}{/* one quiet line, under the tabs — never over content */}
      {tab === 'trip' ? (   /* Sasha 236 · the trip board: S1's TripPanel itself (flights, stays, bookings, forms and receipts, from /plan + /journeys) */
        <section className="s2-trip" style={{ flex: 1, minHeight: 0, overflowY: 'auto', minWidth: 0, padding: '0 12px 16px' }}>
          <style>{TRIP_BOARD_CSS}</style>
          <TripPanel richItinerary={null} openDays={openDays} travellerCount={0 /* Sasha 249 · no page default: the trip's own party, else "—" */}
            toggleDay={(d: number) => setOpenDays(s => { const n = new Set(s); if (n.has(d)) n.delete(d); else n.add(d); return n })} />
        </section>
      ) : tab === 'keep' ? (   /* Sasha 235 · My Keep: the same screen as S1's /keep — masks, what each was used for and when, add, delete */
        <section style={{ flex: 1, minHeight: 0, overflowY: 'auto', minWidth: 0 }}>
          <div className="mx-3 mb-4 rounded-2xl bg-white pb-4 pt-2 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
            <h2 className="px-4 pb-1 pt-3 text-xl font-bold">My Keep</h2>
            <KeepScreen leadClassName="px-4 pb-2 text-sm opacity-60" />{/* Sasha 246 · its line names THEIR item, never a fixed example */}
          </div>
        </section>
      ) : tab === 'activity' ? <section style={{ flex: 1, minHeight: 0, overflowY: 'auto', minWidth: 0 }}><Activity /></section> : (
        <>
          <section style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', minWidth: 0, padding: '0 16px 12px' }}>
            {msgs.length === 0 ? (
              <div style={{ textAlign: 'center', paddingTop: '18vh' }}>
                <div style={{ fontSize: 28, fontWeight: 600, fontFamily: "'Playfair Display',Georgia,serif", lineHeight: 1.25 }}>{GREETING}</div>
                <p style={{ color: C.dim, marginTop: 10 }}>A table tonight, a spa on Saturday, an email to someone, a booking in your calendar.</p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 22 }}>
                  {CHIPS.map((_, j) => CHIPS[(chipAt + j) % CHIPS.length]).map(c => (
                    <button key={c} onClick={() => { speaker.unlock(); listenOnTap(); send(c) }} style={{ padding: '9px 14px', borderRadius: 999, border: `1px solid ${C.line}`, background: C.card, color: '#fff', fontSize: 14.5, transition: 'all .4s' }}>{c}</button>))}
                </div>
              </div>
            ) : msgs.map((m, i) => (
              <div key={i} style={{ margin: '10px 0', minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                {m.text || m.role === 'user' ? (
                  <div style={{ maxWidth: '88%', padding: '10px 14px', borderRadius: 18, background: m.role === 'user' ? 'linear-gradient(135deg,#6d4aff,#9b4dff)' : C.card, border: m.role === 'user' ? 'none' : `1px solid ${C.line}`, lineHeight: 1.45 }}>
                    {m.text}</div>
                ) : <div aria-busy="true" data-sasha-working style={{ color: C.dim, padding: '8px 4px' }}>{m.hold || '…'}</div>}{/* Sasha 259 · ONE working mark: the holding line, else "…" (aria-busy says she's working) */}
                {/* Sasha 230 · a pick sends the card's name QUOTED: a listing like "Comida Hindu - Restaurante India, NAMASTE INDIA(…)" + ", please." read as TWO places — she asked which, the yes didn't answer it, the loop */}
                {m.cards.length ? <div style={{ width: '100%', minWidth: 0, maxWidth: '100%' }}>{m.cards.map((c, j) => <CardView key={j} c={c} choose={t => { speaker.unlock(); send(`This one: “${t}”`) }} pick={(t, id) => { speaker.unlock(); send(`This one: “${t}”`, { place_id: id }) }} send={t => { speaker.unlock(); send(t) }} tap={(title, rid, route) => { speaker.unlock(); send(title, undefined, route === 'call_again' ? { act_id: rid, choice: route } : { read_back_id: rid, choice: route }) }} />)}</div> : null}
              </div>))}
            <div ref={end} />
          </section>
          {asleep ? (   /* Sasha 268 · item 8: paused, said plainly — the mic off, her voice stopped, her live face let go (S2Hello) */
            <div role="status" data-sasha-paused style={{ margin: '0 16px 8px', padding: '10px 12px', borderRadius: 12, border: `1px solid ${C.gold}`, background: 'rgba(232,185,49,.08)', fontSize: 14, lineHeight: 1.4, fontWeight: 600 }}>{ASLEEP_LINE}</div>) : null}
          {micNote ? (   /* Sasha 266 · the mic is "on" only when it hears; otherwise this, plainly, with how to allow it */
            <div role="status" data-mic-stuck style={{ margin: '0 16px 8px', padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(240,120,120,.45)', background: 'rgba(240,120,120,.08)', fontSize: 14, lineHeight: 1.4 }}>
              <div style={{ fontWeight: 700 }}>{micNote}</div>
              {micNote === BLOCKED ? <div style={{ color: C.dim, marginTop: 4 }}>{stepsFor()}</div> : null}
            </div>) : null}
          {/* Sasha 259 · Tyler (row 884): ONE row of ordinary controls — the moon, her voice, her face — nothing floating over send */}
          {/* Sasha 273 · item 5: the row fits a 390 px phone with nothing shrunk under its words (found at 390: the Pause button squeezed to
              36 px, "Pause Sasha" spilling over the mic's label) — no item shrinks; her sound is its icon (its words are its label) */}
          <div data-s2-controls style={{ flex: 'none', display: 'flex', alignItems: 'center', gap: 6, padding: '0 16px 6px', fontSize: 13, flexWrap: 'nowrap', minWidth: 0 }}>
            <SleepButton asleep={asleep} onToggle={() => sleepEvent('tap_pause')} size={36} style={{ flexShrink: 0, padding: '0 10px' }} />
            {voiceBlocked && !muted ? (
              <button onClick={() => { speaker.unlock(); speaker.replayBlocked() }} aria-label="Tap to hear her" title="Tap to hear her" style={{ background: 'none', border: 0, color: C.gold, padding: 4, fontWeight: 700, whiteSpace: 'nowrap', flexShrink: 0, fontSize: 17 }}>
                🔈</button>
            ) : (   /* her SPEAKER (Sasha 230's remembered mute) — its own word, never "Voice": that word is the mic's */
            <button onClick={() => { const m = !muted; setMuted(m); speaker.setMuted(m); if (!m) speaker.unlock(); try { localStorage.setItem('s2_muted', m ? '1' : '0') } catch { /* private mode */ } }} aria-pressed={muted} aria-label={muted ? 'Her sound is off — turn it on' : 'Her sound is on — mute it'} title={muted ? 'Sound off' : 'Sound on'} style={{ background: 'none', border: 0, color: muted ? C.dim : C.gold, padding: 4, fontWeight: 600, whiteSpace: 'nowrap', flexShrink: 0, fontSize: 17, opacity: muted ? 0.6 : 1 }}>
              {muted ? '🔇' : '🔊'}</button>)}
            <button onClick={() => { listenOnTap(); void newChat() }} disabled={busy || clearing} aria-label="New chat" title="Clear this conversation — your bookings and trips stay"
              style={{ background: 'none', border: 0, color: busy || clearing ? C.dim : C.gold, padding: 4, fontWeight: 600, whiteSpace: 'nowrap', flexShrink: 0 }}>＋ New chat</button>{/* Sasha 265 · item 3 */}
            <span style={{ flex: 1 }} />
            <span id="s2-face-slot" style={{ display: 'inline-flex', minWidth: 40, minHeight: 40, flexShrink: 0 }} />{/* her corner: S2Hello's circle sits over this space (Sasha 271 · measured, never portalled) */}
          </div>
          <footer style={{ flex: 'none', padding: '10px 12px', paddingBottom: 'calc(10px + env(safe-area-inset-bottom))', borderTop: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* Sasha 273 · item 3: the voice label is the MIC's real state (lib/presence-rule.mjs voiceOf, from VoiceButton's strict `hearing`),
                on the mic itself — "Voice on" and its green ring only while it hears; otherwise "Tap to talk" (the tap starts or resumes it) */}
            {(() => { const vo = voiceOf({ asleep, dormant, micLive }); return (
            <div className="s2-mic" data-live={vo.live ? '1' : '0'} data-cue={!vo.live && !asleep && !!micNote ? '1' : '0'} onPointerDown={() => { micUsed.current = true; speaker.unlock() }} style={{ flex: 'none', width: 56, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
              {dormant ? null : <VoiceButton quiet onMicError={setMicNote} onTranscript={send} onSetGate={g => { micGate.current = g; g(false) }} readyToListen muted={busy} autoStart={woke} asleep={asleep} onWake={() => sleepEvent('press_mic')}
                strict ctlRef={voiceCtl} onConnectedChange={setMicLive} />}{/* Sasha 273 · item 3: "on" only while it hears */}{/* resting: unmounted — the mic is off · Sasha 246: asleep, the mic off (pressing it wakes her) */}
              <span data-voice-state={vo.live ? 'live' : asleep ? 'paused' : 'tap'} aria-live="polite"
                style={{ fontSize: 10.5, lineHeight: '12px', fontWeight: 700, whiteSpace: 'nowrap', color: vo.live ? '#34d399' : asleep ? C.dim : C.gold }}>{vo.words}</span>
            </div>) })()}
            <Clip busy={busy} send={send} say={t => setMsgs(ms => [...ms, { role: 'sasha', text: t, cards: [] }])} />
            <form onSubmit={e => { e.preventDefault(); speaker.unlock(); send(input) }} style={{ flex: 1, display: 'flex', gap: 8 }}>
              <input ref={typeBox} value={input} onChange={e => { if (asleepRef.current) sleepEvent('typed'); setInput(e.target.value) }} placeholder="Ask Sasha anything…" aria-label="Message Sasha"
                style={{ flex: 1, minWidth: 0, padding: '12px 14px', borderRadius: 999, border: `1px solid ${C.line}`, background: C.card, color: '#fff', fontSize: 16 }} />
              <button type="submit" disabled={!input.trim()} aria-label="Send"
                style={{ padding: '0 16px', borderRadius: 999, border: 0, background: C.gold, color: '#111', fontWeight: 700, opacity: !input.trim() ? 0.5 : 1 }}>➤</button>{/* Sasha 257 · sendable while she answers: it goes next */}
            </form>
          </footer>
          <style>{`.s2-mic button{width:56px;height:56px;border-radius:50%}.s2-mic[data-live="1"] button{box-shadow:0 0 0 3px #34d399}`
            /* Sasha 274 · item 4: the browser truly refused (the mic's own words say so: blocked, suspended until a tap) — the mic itself
               pulses gently with "Tap to talk": unmistakable, never a modal */
            + `.s2-mic[data-cue="1"] button{animation:s2cue 1.6s ease-in-out infinite}.s2-mic[data-cue="1"] [data-voice-state]{font-size:12px}`
            + `@keyframes s2cue{0%,100%{box-shadow:0 0 0 0 rgba(232,185,49,.55)}50%{box-shadow:0 0 0 9px rgba(232,185,49,0)}}`
            + `@media (prefers-reduced-motion: reduce){.s2-mic[data-cue="1"] button{animation:none;box-shadow:0 0 0 3px #e8b931}}`}</style>
        </>
      )}
    </main>{hello}
    {handover ? (   /* Sasha 236 · Tap to finish in a sheet over her (the CAPTCHA, terms, their button) — then back to her, as /next */
      <div role="dialog" aria-label="Finish the booking" style={{ position: 'fixed', inset: 0, zIndex: 60, background: C.bg, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', paddingTop: 'max(12px, env(safe-area-inset-top))', borderBottom: `1px solid ${C.line}`, color: '#fff' }}>
          <b>Finish the booking</b>
          <button type="button" onClick={() => setHandover(null)} style={{ padding: '6px 14px', borderRadius: 999, border: `1px solid ${C.gold}`, background: 'transparent', color: C.gold, fontWeight: 600 }}>Back to Sasha</button>
        </div>
        <iframe src={handover} title="Finish the booking" allow="clipboard-write" style={{ flex: 1, border: 0, width: '100%', background: '#fff' }} />
      </div>
    ) : null}
    {/* Sasha 259 · the moon is in the voice row now (no longer fixed over "Voice off") */}
    {dormant ? <button onClick={wake} aria-label="Sasha is resting — tap to bring her back" style={{ position: 'fixed', inset: 0, zIndex: 45, background: 'transparent', border: 0, padding: 0, cursor: 'pointer' }}>
      <span style={{ position: 'absolute', left: '50%', top: '46%', transform: 'translate(-50%, -50%)', padding: '10px 18px', borderRadius: 999, border: `1px solid ${C.line}`, background: C.card, color: C.dim, fontSize: 14.5, whiteSpace: 'nowrap' }}>Tap me if you need me</span>
    </button> : null}</>
  )
}

/** Sasha 228 · /s2?handoff=<code> — the phone end of /next's "Add from your phone": straight to Add my passport, for the account
 *  that showed the QR code. Not signed in: the one-time code is the only permission, and it covers this one photo. */
export function S2Handoff({ code }: { code: string }) {
  const [st, setSt] = useState<{ s: 'checking' } | { s: 'open'; what: 'passport' | 'loyalty' } | { s: 'gone'; why: string } | { s: 'done'; item: string }>({ s: 'checking' })
  useEffect(() => {
    fetch(`/api/keep-handoff/${encodeURIComponent(code)}`, { cache: 'no-store' }).then(r => r.json())
      .then(j => setSt(j?.ok ? { s: 'open', what: j.kind === 'loyalty' ? 'loyalty' : 'passport' } : { s: 'gone', why: j?.message || 'This link has expired.' }))
      .catch(() => setSt({ s: 'gone', why: 'This link couldn’t be checked — try scanning it again.' }))
  }, [code])
  return (
    <main style={{ minHeight: '100dvh', background: C.bg, color: '#fff', fontFamily: 'system-ui', maxWidth: 560, width: '100%', margin: '0 auto', padding: '0 16px', overflowX: 'hidden' }}>
      <header style={{ padding: '14px 0', paddingTop: 'max(56px, calc(env(safe-area-inset-top) + 44px))' }}>
        <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "'Playfair Display',Georgia,serif" }}>Sasha</div>
        <div style={{ color: C.dim, fontSize: 14, marginTop: 4 }}>Adding to your Keep, from your phone</div>
      </header>
      {st.s === 'checking' && <div style={{ color: C.dim, fontSize: 14 }}>Opening…</div>}
      {st.s === 'gone' && <Box k="Add from your phone" h="This link can't be used"><div style={{ fontSize: 14, color: C.dim }}>{st.why}</div></Box>}
      {st.s === 'open' && <KeepCapture what={st.what} base={`/api/keep-handoff/${encodeURIComponent(code)}/scan`} onSaved={item => setSt({ s: 'done', item })} />}
      {st.s === 'done' && <>
        <Box k="Added to your Keep" h={untag(st.item)} tone="rgba(126,226,168,.5)"><div style={{ fontSize: 13.5, color: C.dim }}>Encrypted. Sasha only ever sees the mask.</div></Box>
        <div style={{ color: C.dim, fontSize: 14, margin: '14px 4px' }}>Sasha has it on your computer now — you can close this page.</div></>}
    </main>
  )
}
