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
import { findVenues, readVenue, refusal, styleVenues, type Candidate, type Ranking, type Rung, type Style } from '@/lib/booking-client'
import { setChatBookingHandler, takeTypedYes } from '@/lib/chat-booking-bus'
import { GatedButton } from '../booking-helper/GatedButton'
import ChatBookingCall from './ChatBookingCall'
import { SignInToBook, WhoIsBooking } from './SignedInLine'

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

// S-68 step 8 · the chips; one that cannot sort yet says what it needs
const CHIPS: [string, string, string][] = [['rated', '★ Best rated', 'ratings in the results'],
  ['closest', '📍 Closest', 'a hotel or address to measure from (say “near …”)'], ['price', '€ Price', 'price levels in the results'],
  ['open', '🕑 Open then', 'a day and time (say “open Tuesday 17:00”)']]
const GROUP_WORDS: Record<string, string> = { closed_then: 'closed then', hours_unknown: 'hours not listed', closed_temporarily: 'temporarily closed' }

const RUNG_NAME: Record<string, string> = { form: 'their booking form', link: 'their booking page', platform: 'a booking platform',
  phone: 'a phone call', email: 'an email', whatsapp: 'WhatsApp (you send it)' }
const ORDINAL: Record<string, number> = { first: 0, '1st': 0, one: 0, second: 1, '2nd': 1, two: 1, third: 2, '3rd': 2, three: 2,
  fourth: 3, '4th': 3, four: 3, fifth: 4, '5th': 4, five: 4 }

export default function ChatBooking({ find }: { find: Find }) {
  const [state, setState] = useState<State>({ phase: 'finding' })
  const stateRef = useRef(state)
  // S-68 step 9 · style per place_id, read for the cards SHOWN only; 'reading' while their sites are read
  const [styles, setStyles] = useState<Record<string, Style | 'reading'>>({})
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
  }, [find.what, find.where, find.country, find.near, find.open_at, find.priority])

  function sortBy(chip: string) {
    const s = stateRef.current
    if (s.phase !== 'found' || !s.ranking?.orders[chip]) return
    setState({ ...s, chip, cards: inOrder(s.all, s.ranking, chip, s.show) })
  }

  const shownIds = state.phase === 'found' ? state.cards.map((c) => c.place_id).join(',') : ''
  useEffect(() => {
    const s = stateRef.current
    if (s.phase !== 'found') return
    const need = s.cards.filter((c) => !(c.place_id in styles))
    if (!need.length) return
    setStyles((m) => ({ ...m, ...Object.fromEntries(need.map((c) => [c.place_id, 'reading' as const])) }))
    ;(async () => {
      try {
        const r = await styleVenues(find.what, need.map((c) => ({ place_id: c.place_id, website: c.website })))
        const got = (r.ok ? (r.json.styles ?? {}) : {}) as Record<string, Style>
        const why = r.ok ? 'not read' : refusal(r.json, r.status)
        setStyles((m) => ({ ...m, ...Object.fromEntries(need.map((c) => [c.place_id, got[c.place_id] ?? { why }])) }))
      } catch (e) {
        setStyles((m) => ({ ...m, ...Object.fromEntries(need.map((c) => [c.place_id, { why: (e as Error).message }])) }))
      }
    })()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run only when the cards shown change
  }, [shownIds])

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
  if (state.phase === 'founder_only') return <div style={box}><SignInToBook /></div>
  if (state.phase === 'finding') return <div style={box}>Looking for {find.what} in {find.where}…</div>
  if (state.phase === 'refused') return <div style={box}>{state.words}</div>
  const cards = state.cards
  const lookup = state.phase === 'read' ? state.pick : null
  return (
    <div style={box}>
      <WhoIsBooking />
      {cards.length === 0
        ? <div>Google has no listing for {find.what} in {find.where}.</div>
        : <div style={{ fontSize: 13, opacity: 0.75, marginBottom: 6 }}>{find.what} in {find.where} — from Google Maps; nobody has been contacted. Choose one, or say “the second one”.</div>}
      {state.phase === 'found' && state.ranking && <div style={{ fontSize: 13, marginBottom: 4 }}>{state.ranking.count} · {state.ranking.explainers[state.chip]}</div>}
      {state.phase === 'found' && find.open_at && <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>Open then by their listed hours; availability is confirmed only when Sasha books.</div>}
      {state.phase === 'found' && state.near && !state.near.found && <div style={{ fontSize: 13, marginBottom: 6 }}>No distances: {state.near.why}</div>}
      {state.phase === 'found' && state.ranking && cards.length > 0 && (
        <div style={{ margin: '4px 0 8px' }}>
          {!find.priority && <div style={{ fontSize: 13, marginBottom: 4 }}>What matters most? Tap one, or say it.</div>}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {CHIPS.map(([chip, label, needs]) => (
              <GatedButton key={chip} label={state.chip === chip ? `✓ ${label}` : label} onClick={() => sortBy(chip)}
                needs={[!state.ranking?.orders[chip] && needs]} done={state.chip === chip && 'sorted this way'} />
            ))}
          </div>
        </div>
      )}
      <ol style={{ margin: 0, paddingLeft: 18 }}>
        {cards.map((c) => {
          // S-68 step 8 · every value said, a missing one in words; a place not open then is greyed, never dropped
          const group = state.phase === 'found' ? state.ranking?.groups[c.place_id] : undefined
          const grey = group === 'closed_then' || group === 'closed_temporarily'
          const near = state.phase === 'found' && state.near?.found
          const facts = [c.rating_words ?? 'no rating', near ? (c.distance ?? 'distance not known') : null, c.price_words ?? 'price level not listed']
          return (
            <li key={c.place_id} style={{ marginBottom: 10, opacity: grey ? 0.55 : 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span><strong>{c.name ?? 'no name listed'}</strong>{c.type ? <span style={{ opacity: 0.7 }}> · {c.type}</span> : null}
                  {group && group !== 'main' ? <span style={{ color: '#9a1c1c' }}> · {GROUP_WORDS[group]}</span> : null}</span>
                <span style={{ fontSize: 12, opacity: 0.6, whiteSpace: 'nowrap' }}>Google Maps</span>
              </div>
              <div style={{ fontSize: 13 }}>{facts.filter(Boolean).join(' · ')}</div>
              {c.open_at ? <div style={{ fontSize: 13 }}>{c.open_at.words}</div> : null}
              {c.books ? <div style={{ fontSize: 13 }}>How Sasha books: {c.books.words}</div> : null}
              {(() => {
                const st = styles[c.place_id]
                if (!st) return null
                if (st === 'reading') return <div style={{ fontSize: 13, opacity: 0.7 }}>Style: reading their website…</div>
                if (st.tags?.length) return <div style={{ fontSize: 13 }}>{st.label}: {st.tags.map((t) => t.tag).join(', ')}
                  {st.source ? <> · <a href={st.source} target="_blank" rel="noopener noreferrer" title={st.tags.map((t) => `${t.tag}: “${t.quote}”`).join('\n')}>their website ↗</a></> : null}</div>
                return <div style={{ fontSize: 12, opacity: 0.7 }}>Style: {st.why}</div>
              })()}
              <div style={{ fontSize: 12, opacity: 0.75 }}>{c.address ?? 'no address listed'}</div>
              <span style={{ display: 'inline-flex', gap: 10, alignItems: 'flex-start', marginTop: 4 }}>
                <GatedButton label="Choose" onClick={() => { pick(c).catch(() => { /* visible state set inside */ }) }}
                  needs={[state.phase === 'reading' && 'the read in progress to finish']} />
                <a href={c.listing_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13 }}>Their listing ↗</a>
              </span>
            </li>
          )
        })}
      </ol>
      {cards.length > 0 && <div style={{ fontSize: 12, opacity: 0.6 }}>Places, ratings, prices and hours: Google Maps.</div>}
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
