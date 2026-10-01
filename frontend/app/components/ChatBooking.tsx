'use client'

/**
 * S-66 (EU) steps 1, 3, 4 · BOOKING INSIDE SASHA'S CHAT — find, pick, read. Repo-only: a CTO drop does not ship this
 * file, and Stage B re-inserts it into SashaChat (CLAUDE.md; scripts/check-outcome-surfaces.mjs fails the build if the
 * insertion is missing).
 *
 *   step 1 · THE GATE: every request goes through /api/booking-proxy (lib/booking-client). No founder session (401) →
 *            "Booking is only open to the founder's account for now." and no buttons — nothing else.
 *   step 3 · FIND: the conductor's `booking_find` → POST /venues/find → up to five cards, each "from its Google
 *            listing". Nothing is contacted. Refusals are shown as they come.
 *   step 4 · PICK → READ: a tap, or "the second one" typed → POST /venues/read with THAT listing's place_id → the
 *            server's own sentence and its rungs: available ones by name, unavailable ones with their reason.
 *
 *   steps 7–9 · when the venue can be PHONED (the server says so in its rungs), ChatBookingCall asks the details once,
 *            shows the server's read-back, takes the yes (button or typed) and shows the result and the itinerary line.
 *            When it cannot, the server's reason is shown and the booking page is the way on.
 */
import { useEffect, useRef, useState } from 'react'
import { FOUNDER_ONLY, findVenues, readVenue, refusal, type Candidate, type Ranking, type Rung } from '@/lib/booking-client'
import { setChatBookingHandler, takeTypedYes } from '@/lib/chat-booking-bus'
import { GatedButton } from '../booking-helper/GatedButton'
import ChatBookingCall from './ChatBookingCall'

type Find = { what: string; where: string; country?: string; near?: string; open_at?: string; priority?: string; draft?: unknown }
type Read = { read_id: string; venue: string; country: string | null; say: string; rungs: Rung[]; listing?: { name?: string } | null }
type State =
  | { phase: 'finding' } | { phase: 'founder_only' } | { phase: 'refused'; words: string }
  | { phase: 'found'; cards: Candidate[]; near?: Near; ranking?: Ranking; all: Candidate[]; chip: string; show: number } | { phase: 'reading'; cards: Candidate[]; pick: Candidate }
  | { phase: 'read'; cards: Candidate[]; pick: Candidate; read: Read } | { phase: 'read_refused'; cards: Candidate[]; words: string }

type Near = { asked: string; found: boolean; why?: string }
// S-68 steps 6–7 · the cards in a chip's order, from the same 20 — no new search
function inOrder(all: Candidate[], ranking: Ranking | undefined, chip: string, show: number): Candidate[] {
  if (!ranking?.orders[chip]) return all.slice(0, show)
  const byId = new Map(all.map((c) => [c.place_id, c]))
  return ranking.orders[chip].map((id) => byId.get(id)).filter((c): c is Candidate => !!c).slice(0, show)
}
// a priority TYPED in answer to "What matters most?"
const TYPED_CHIP: [string, RegExp][] = [['price', /\b(cheap|cheapest|price|budget|affordable)\b/i],
  ['rated', /\b(best rated|rating|rated|reviews|best)\b/i], ['closest', /\b(closest|nearest|distance|near)\b/i],
  ['open', /\b(open|opening|hours)\b/i]]

const RUNG_NAME: Record<string, string> = { form: 'their booking form', link: 'their booking page', platform: 'a booking platform',
  phone: 'a phone call', email: 'an email', whatsapp: 'WhatsApp (you send it)' }
const ORDINAL: Record<string, number> = { first: 0, '1st': 0, one: 0, second: 1, '2nd': 1, two: 1, third: 2, '3rd': 2, three: 2,
  fourth: 3, '4th': 3, four: 3, fifth: 4, '5th': 4, five: 4 }

export default function ChatBooking({ find }: { find: Find }) {
  const [state, setState] = useState<State>({ phase: 'finding' })
  const stateRef = useRef(state)
  useEffect(() => { stateRef.current = state }, [state])

  useEffect(() => {
    let off = false
    ;(async () => {
      setState({ phase: 'finding' })
      try {
        const r = await findVenues(find.what, find.where, find.country, find.near, find.open_at)
        if (off) return
        if (r.status === 401) { setState({ phase: 'founder_only' }); return }
        if (!r.ok) {
          const rule = String(r.json.rule ?? '')
          setState({ phase: 'refused', words: rule.startsWith('places_') ? "I can't search for places right now."
            : rule.endsWith('_invalid') ? 'Tell me what kind of place, and where.' : refusal(r.json, r.status) })
          return
        }
        // S-68 steps 2, 6 · the server searches 20, ranks them, and says how many to show
        const show = typeof r.json.show === 'number' ? r.json.show : 5
        const all = (r.json.candidates ?? []) as Candidate[]
        const ranking = (r.json.ranking ?? undefined) as Ranking | undefined
        // S-68 step 7 · the priority the guest stated, else best rated until they say
        const chip = ranking && find.priority && ranking.orders[find.priority] ? find.priority : (ranking?.default ?? 'rated')
        setState({ phase: 'found', cards: inOrder(all, ranking, chip, show), near: (r.json.near ?? undefined) as Near | undefined,
          ranking, all, chip, show })
      } catch (e) {
        if (!off) setState({ phase: 'refused', words: `I couldn't search just now: ${(e as Error).message}.` })
      }
    })()
    return () => { off = true }
  }, [find.what, find.where, find.country, find.near, find.open_at])

  function sortBy(chip: string) {
    const s = stateRef.current
    if (s.phase !== 'found' || !s.ranking?.orders[chip]) return
    setState({ ...s, chip, cards: inOrder(s.all, s.ranking, chip, s.show) })
  }

  async function pick(c: Candidate) {
    const cards = 'cards' in stateRef.current ? stateRef.current.cards : []
    setState({ phase: 'reading', cards, pick: c })
    try {
      // Sasha 64 · stored by place_id with the guest's own words ("asked_for"); the listing's name is shown, never stored
      const r = await readVenue({ name: c.name ?? find.what, city: find.where, country: c.country ?? find.country, place_id: c.place_id, asked_for: find.what })
      if (r.status === 401) { setState({ phase: 'founder_only' }); return }
      if (!r.ok) { setState({ phase: 'read_refused', cards, words: refusal(r.json, r.status) }); return }
      setState({ phase: 'read', cards, pick: c, read: r.json as unknown as Read })
    } catch (e) {
      setState({ phase: 'read_refused', cards, words: (e as Error).message })
    }
  }

  // "the second one" typed in the chat picks a card; anything else is not ours (the conductor gets it)
  useEffect(() => {
    setChatBookingHandler((text: string) => {
      if (takeTypedYes(text)) return true   // step 9 · a typed yes to the pending read-back card
      const s = stateRef.current
      // S-68 step 7 · a SHORT answer ("closest", "the cheapest", "best rated please") re-sorts; anything longer is a
      // new message for Sasha (e.g. "the best restaurant in Hanoi?")
      if (s.phase === 'found' && s.ranking && text.trim().split(/\s+/).length <= 4) {
        const hit = TYPED_CHIP.find(([chip, rx]) => rx.test(text) && s.ranking?.orders[chip])
        if (hit && !/\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)\b/i.test(text)) { sortBy(hit[0]); return true }
      }
      if (s.phase !== 'found' && s.phase !== 'read' && s.phase !== 'read_refused') return false
      const m = text.toLowerCase().match(/\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|one|two|three|four|five)\b/)
      if (!m || !/\b(one|pick|choose|that|the)\b/.test(text.toLowerCase())) return false
      const card = s.cards[ORDINAL[m[1]]]
      if (!card) return false
      pick(card).catch(() => { /* every path above sets a visible state */ })
      return true
    })
    return () => setChatBookingHandler(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- one handler for the thread's life; it reads the state through a ref
  }, [])

  const box = { border: '1px solid rgba(0,0,0,.12)', borderRadius: 10, padding: 12, margin: '8px 0' } as const
  if (state.phase === 'founder_only') return <div style={box}>{FOUNDER_ONLY}</div>
  if (state.phase === 'finding') return <div style={box}>Looking for {find.what} in {find.where}…</div>
  if (state.phase === 'refused') return <div style={box}>{state.words}</div>
  const cards = state.cards
  const lookup = state.phase === 'read' ? state.pick : null
  return (
    <div style={box}>
      {cards.length === 0
        ? <div>Google has no listing for {find.what} in {find.where}.</div>
        : <div style={{ fontSize: 13, opacity: 0.75, marginBottom: 6 }}>{cards.length} {cards.length === 1 ? 'place' : 'places'} for {find.what} in {find.where} — from Google Maps; nobody has been contacted. Tap one, or say “the second one”.</div>}
      {state.phase === 'found' && state.ranking && <div style={{ fontSize: 13, marginBottom: 4 }}>{state.ranking.count} · {state.ranking.explainers[state.chip]}</div>}
      {state.phase === 'found' && find.open_at && <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>Open then by their listed hours; availability is confirmed only when Sasha books.</div>}
      {state.phase === 'found' && state.near && !state.near.found && <div style={{ fontSize: 13, marginBottom: 6 }}>No distances: {state.near.why}</div>}
      <ol style={{ margin: 0, paddingLeft: 18 }}>
        {cards.map((c) => (
          <li key={c.place_id} style={{ marginBottom: 8 }}>
            <strong>{c.name}</strong>{c.type ? <span style={{ opacity: 0.7 }}> · {c.type}</span> : null}
            {c.status && c.status !== 'OPERATIONAL' ? <span style={{ color: '#9a1c1c' }}> · {c.status.toLowerCase().replace(/_/g, ' ')}</span> : null}
            <div style={{ fontSize: 13, opacity: 0.85 }}>{c.address ?? 'no address listed'} · {c.phone ?? 'no phone listed'}{c.website ? ` · ${c.website}` : ''}</div>
            {c.rating_words || c.price_words ? <div style={{ fontSize: 13 }}>{[c.rating_words, c.price_words].filter(Boolean).join(' · ')}</div> : null}
            {c.open_at ? <div style={{ fontSize: 13 }}>{c.open_at.words}</div> : null}
            {c.books ? <div style={{ fontSize: 13 }}>How Sasha books: {c.books.words}</div> : null}
            {c.distance ? <div style={{ fontSize: 13 }}>{c.distance}{state.phase === 'found' && state.near ? ` from ${state.near.asked}` : ''}</div> : null}
            <div style={{ fontSize: 12, opacity: 0.6 }}>Google Maps</div>
            <GatedButton label={`Read ${c.name ?? 'this one'}`} onClick={() => { pick(c).catch(() => { /* visible state set inside */ }) }}
              needs={[state.phase === 'reading' && 'the read in progress to finish']} />
          </li>
        ))}
      </ol>
      {state.phase === 'reading' && <div>Reading how {state.pick.name} takes bookings…</div>}
      {state.phase === 'read_refused' && <div>I couldn&rsquo;t read them: {state.words}</div>}
      {state.phase === 'read' && (
        <div style={{ marginTop: 8 }}>
          <div style={{ fontWeight: 600 }}>{state.read.say}</div>
          <ul style={{ margin: '6px 0', paddingLeft: 18 }}>
            {state.read.rungs.map((r, i) => (
              <li key={i}>{RUNG_NAME[r.rung] ?? r.rung}: {r.value} <span style={{ opacity: 0.6 }}>— on {r.source_label}</span>
                {!r.available && r.why_not ? <div style={{ fontSize: 13, opacity: 0.8 }}>Not available: {r.why_not}</div> : null}</li>
            ))}
          </ul>
          {(() => {
            const ph = state.read.rungs.find((r) => r.rung === 'phone' && r.available)
            return ph ? <ChatBookingCall readId={state.read.read_id} country={state.read.country ?? find.country ?? null} phone={ph}
              venue={state.pick.name ?? state.read.venue} draft={(find.draft ?? null) as never} whatText={find.what} /> : null
          })()}
          {lookup && <a href={`/booking-helper?book=phone&lookup=${encodeURIComponent(lookup.name ?? '')}&city=${encodeURIComponent(find.where)}&country=${encodeURIComponent(lookup.country ?? find.country ?? '')}`}
            target="_blank" rel="noopener noreferrer">Book it on the booking page ↗</a>}
          <div style={{ fontSize: 12, opacity: 0.6, marginTop: 4 }}>Nothing has been contacted yet.</div>
        </div>
      )}
    </div>
  )
}
