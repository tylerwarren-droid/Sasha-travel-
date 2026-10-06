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
import { bookingReq, findVenues, readVenue, refusal, styleVenues, type Candidate, type Ranking, type Rung, type Style } from '@/lib/booking-client'
import { setChatBookingHandler, takeTypedYes } from '@/lib/chat-booking-bus'
import { GatedButton } from '../booking-helper/GatedButton'
import { ChatBookingDo } from './ChatBookingDo'
import ChatBookingCall from './ChatBookingCall'
import ChatBookingLink from './ChatBookingLink'
import { SignInToBook } from './SignedInLine'

type Find = { what: string; where?: string; country?: string; near?: string; open_at?: string; priority?: string; draft?: unknown; named?: boolean
  bare_time?: { day: string; hour: number; minute: number } }
type Read = { read_id: string; venue: string; country: string | null; say: string; rungs: Rung[]; listing?: { name?: string } | null
  /** Sasha 161 · the server's decision and its one plain line (decide.py — the same words as WhatsApp) */
  plan?: { route: string | null; line: string | null } }
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

const MARK = { position: 'absolute', right: 6, bottom: 6, fontSize: 10, lineHeight: '14px', padding: '1px 6px', borderRadius: 6,
  background: 'rgba(0,0,0,.55)', color: '#fff', maxWidth: '70%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } as const
/** the city part of a Google address ("…, 28005 Madrid, Spain" → "Madrid"), for a venue found by its name alone */
const cityOf = (address: string | null | undefined): string | undefined => {
  const parts = (address ?? '').split(',').map((x) => x.trim()).filter(Boolean)
  const c = parts.length >= 2 ? parts[parts.length - 2].replace(/[\d-]+/g, '').trim() : undefined
  return c && c.length >= 2 ? c : undefined
}

export default function ChatBooking({ find }: { find: Find }) {
  const [state, setState] = useState<State>({ phase: 'finding' })
  const stateRef = useRef(state)
  // S-68 step 9 · style per place_id, read for the cards SHOWN only; 'reading' while their sites are read
  const [styles, setStyles] = useState<Record<string, Style | 'reading'>>({})
  // Sasha 88 · once a call is placed or scheduled, "nobody has been contacted" is no longer true and is not shown
  const [contacted, setContacted] = useState<'calling' | 'scheduled' | null>(null)
  // Sasha 88 · a site's picture that fails to load is simply not shown (no broken image, no stand-in)
  const [badPhoto, setBadPhoto] = useState<Record<string, true>>({})
  // Sasha 156 · Google's photo of the listing, shown while (or where) the venue's own picture isn't there
  const [gphotos, setGphotos] = useState<Record<string, string>>({})
  // Sasha 95 · the slot link leads when a platform is their booking route; a call only if the guest asks for one
  const [callInstead, setCallInstead] = useState(false)
  // Sasha 100 · the cards arrive after the message the chat scrolled to — bring them (and each next step) into view
  const listRef = useRef<HTMLOListElement | null>(null)
  const readRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => { stateRef.current = state }, [state])

  useEffect(() => {
    let off = false
    ;(async () => {
      setState({ phase: 'finding' })
      try {
        const r = await findVenues(find.what, find.where, find.country, find.near, find.open_at, find.named)
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
  // Sasha 86 · every booking message starts afresh — a new `find` object, even for the same words, drops the last pick,
  // its read and its details card, so nothing from an earlier request (another day, another count) is carried over
  }, [find])

  // Sasha 158 · NAME IT: the one venue named is picked at once — straight to the read-back
  useEffect(() => {
    if (find.named && state.phase === 'found' && state.cards.length === 1) pick(state.cards[0]).catch(() => { /* visible state set inside */ })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase])

  useEffect(() => {
    const el = state.phase === 'found' && state.cards.length ? listRef.current : state.phase === 'read' ? readRef.current : null
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [state.phase])

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
  useEffect(() => {
    const s = stateRef.current
    if (s.phase !== 'found') return
    const names = s.cards.filter((c) => !c.gphoto?.uri).map((c) => c.gphoto?.name).filter((n): n is string => !!n && !(n in gphotos))
    if (!names.length) return
    ;(async () => {
      const r = await bookingReq('/api/booking/venues/gphotos', { names, width: 480 }).catch(() => null)
      const got = (r?.ok ? (r.json.photos ?? {}) : {}) as Record<string, string>
      if (Object.keys(got).length) setGphotos((m) => ({ ...m, ...got }))
    })()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run only when the cards shown change
  }, [shownIds])

  async function pick(c: Candidate) {
    const cards = 'cards' in stateRef.current ? stateRef.current.cards : []
    setState({ phase: 'reading', cards, pick: c })
    try {
      // Sasha 64 · stored by place_id with the guest's own words ("asked_for"); the listing's name is shown, never stored
      const r = await readVenue({ name: c.name ?? find.what, city: find.where || cityOf(c.address) || 'unknown', country: c.country ?? find.country, place_id: c.place_id, asked_for: find.what })
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
  if (state.phase === 'finding') return <div style={box}>One moment…</div>
  if (state.phase === 'refused') return <div style={box}>{state.words}</div>
  const cards = state.cards
  return (
    <div style={box}>
      {/* Sasha 158 · one sentence was said in the chat already; the card says nothing about how it was found */}
      {cards.length === 0
        ? <div>{find.named ? `I couldn't find ${find.what}.` : `I couldn't find any ${find.what} in ${find.where}.`} Try another name or place?</div>
        : null}
      <ol ref={listRef} style={{ margin: 0, paddingLeft: 18 }}>
        {cards.map((c) => {
          // S-68 step 8 · every value said, a missing one in words; a place not open then is greyed, never dropped
          const group = state.phase === 'found' ? state.ranking?.groups[c.place_id] : undefined
          const grey = group === 'closed_then' || group === 'closed_temporarily'
          const near = state.phase === 'found' && state.near?.found
          const facts = [c.rating_words ?? 'no rating', near ? (c.distance ?? 'distance not known') : null, c.price_words ?? 'price level not listed']
          return (
            <li key={c.place_id} style={{ marginBottom: 10, opacity: grey ? 0.55 : 1 }}>
              {(() => {
                // Sasha 88 · the venue's own share picture, from its website — linked to the site; none when it has none
                const st = styles[c.place_id]
                const ph = st && st !== 'reading' ? st.photo : undefined
                if (!ph || badPhoto[c.place_id]) {
                  // Sasha 156 · no picture of their own (yet): the Google listing's photo, credited as Google's terms ask
                  const g = c.gphoto?.uri || (c.gphoto?.name ? gphotos[c.gphoto.name] : undefined)
                  if (!g || badPhoto[`g:${c.place_id}`]) return null
                  return (
                    <a href={c.listing_url} target="_blank" rel="noopener noreferrer" style={{ display: 'block', margin: '2px 0 6px', position: 'relative' }}>
                      {/* eslint-disable-next-line @next/next/no-img-element -- Google's short-lived photo URL; never stored by us */}
                      <img src={g} alt={`${c.name ?? 'This place'} — Google Maps photo`} loading="eager" referrerPolicy="no-referrer"
                        onError={() => setBadPhoto((m) => ({ ...m, [`g:${c.place_id}`]: true }))}
                        style={{ width: '100%', maxHeight: 150, objectFit: 'cover', borderRadius: 8, display: 'block' }} />
                      {/* Sasha 158 · Google's attribution as a small mark ON the photo (its author, as Google's terms ask) */}
                      <span style={MARK} title={`Photo: Google Maps${c.gphoto?.by?.length ? ` · ${c.gphoto.by.join(', ')}` : ''}`}>Google{c.gphoto?.by?.length ? ` · ${c.gphoto.by[0]}` : ''}</span>
                    </a>
                  )
                }
                return (
                  <a href={ph.source} target="_blank" rel="noopener noreferrer" style={{ display: 'block', margin: '2px 0 6px', position: 'relative' }}>
                    {/* eslint-disable-next-line @next/next/no-img-element -- shown from the venue's own host; never fetched or stored by us */}
                    <img src={ph.url} alt={`${c.name ?? 'This place'} — from their website`} loading="lazy" referrerPolicy="no-referrer"
                      onError={() => setBadPhoto((m) => ({ ...m, [c.place_id]: true }))}
                      // Sasha 156 · a logo or a spacer is not a photo of the place: too small → Google's photo instead
                      onLoad={(e) => { const i = e.currentTarget; if (i.naturalWidth < 160 || i.naturalHeight < 90) setBadPhoto((m) => ({ ...m, [c.place_id]: true })) }}
                      style={{ width: '100%', maxHeight: 150, objectFit: 'cover', borderRadius: 8, display: 'block' }} />
                    <span style={MARK} title="Photo from their own website">their site</span>
                  </a>
                )
              })()}
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span>{state.phase === 'found' && state.ranking?.picks?.[state.chip] === c.place_id   /* S-75 step 1 · the server's pick (ranking.py) */
                    ? <span style={{ fontSize: 11, padding: '1px 6px', marginRight: 6, borderRadius: 8, background: '#c9a227', color: '#111' }}>Sasha&rsquo;s pick</span> : null}
                  <strong>{c.name ?? 'no name listed'}</strong>{c.type ? <span style={{ opacity: 0.7 }}> · {c.type}</span> : null}
                  {group && group !== 'main' ? <span style={{ color: '#9a1c1c' }}> · {GROUP_WORDS[group]}</span> : null}</span>
                <span style={{ fontSize: 12, opacity: 0.6, whiteSpace: 'nowrap' }}>Google Maps</span>
              </div>
              <div style={{ fontSize: 13 }}>{facts.filter(Boolean).join(' · ')}</div>
              {c.open_at ? <div style={{ fontSize: 13 }}>{c.open_at.words}</div> : null}
              {(() => {
                const st = styles[c.place_id]
                if (!st) return null
                if (st === 'reading') return null
                // Sasha 158 · their style in a few words; that it was AI-summarised from their own site stays in the ✦ mark
                if (st.tags?.length) return <div style={{ fontSize: 13 }}>{st.tags.map((t) => t.tag).join(' · ')}{' '}
                  <span title={`Summarised by AI from their own website:\n${st.tags.map((t) => `${t.tag}: “${t.quote}”`).join('\n')}`} style={{ opacity: 0.5, fontSize: 11 }}>✦ AI</span></div>
                return null
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
      {/* Sasha 100 · the cards come first; why they're in this order, and the chips, follow */}
      {/* Sasha 158 · no ranking explainer for the guest: the chips say how they're sorted */}
      {state.phase === 'found' && state.near && !state.near.found && <div style={{ fontSize: 13, marginBottom: 6 }}>No distances: {state.near.why}</div>}
      {state.phase === 'found' && state.ranking && cards.length > 0 && (
        <div style={{ margin: '4px 0 8px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {CHIPS.map(([chip, label, needs]) => (
              <GatedButton key={chip} label={state.chip === chip ? `✓ ${label}` : label} onClick={() => sortBy(chip)}
                needs={[!state.ranking?.orders[chip] && needs]} done={state.chip === chip && 'sorted this way'} />
            ))}
          </div>
        </div>
      )}
      {state.phase === 'reading' && <div style={{ opacity: 0.7 }}>One moment…</div>}
      {state.phase === 'read_refused' && <div>I can&rsquo;t book {state.cards.find(() => true) ? 'that one' : 'them'} from here — {state.words}.</div>}
      {state.phase === 'read' && (
        <div ref={readRef} style={{ marginTop: 8 }}>
          {(() => {
            // Sasha 158 · THE LADDER, chosen by Sasha and never explained: their own form → their email (no reply → a call,
            // under the same yes) → a call → their booking platform's page (your press) → WhatsApp where that's their channel
            const r = state.read.rungs
            const fm = r.find((x) => x.rung === 'form' && x.available)
            const em = r.find((x) => x.rung === 'email' && x.available)
            const ph = r.find((x) => x.rung === 'phone' && x.available)
            const ln = r.find((x) => x.rung === 'link' && x.available)
            const wa = r.find((x) => x.rung === 'whatsapp' && x.available)
            const venue = state.pick.name ?? state.read.venue
            const draft = (find.draft ?? null) as { when?: { at?: string }; how_many?: { count?: number } } | null
            // Sasha 158 · "book Casa Lucio tomorrow at 9": at a restaurant, a bare 9 is 21:00 (12 is noon) — the same rule as WhatsApp
            const bt = find.bare_time
            const eatery = /restaurant|bar|caf|bistro|tavern|grill|steak|sushi|pizz|brasserie|tapas|food|bodega/i.test(state.pick.type ?? '')
            const openAt = find.open_at ?? (bt && eatery ? `${bt.day}T${String(bt.hour === 12 ? 12 : bt.hour + 12).padStart(2, '0')}:${String(bt.minute).padStart(2, '0')}` : null)
            // a venue named, at a restaurant: what to book is a table, said in their language (the call needs both)
            const TABLE: Record<string, string> = { ES: 'una mesa', MX: 'una mesa', AR: 'una mesa', PT: 'uma mesa', BR: 'uma mesa', FR: 'une table',
              IT: 'un tavolo', DE: 'einen Tisch', AT: 'einen Tisch' }
            const draftAll = (find.draft ?? null) as Record<string, unknown> | null
            const parts = ((draftAll?.parts ?? draftAll) ?? {}) as Record<string, unknown>
            const callDraft = find.named && eatery && !parts.what
              ? { ...(draftAll ?? {}), parts: { ...parts, what: { activity: 'a table', activity_venue_lang: TABLE[state.read.country ?? ''] ?? 'a table', category: 'restaurant' } } }
              : find.draft
            const plan = state.read.plan ?? { route: null, line: null }
            const pr = plan.route
            if (fm && !callInstead && (!pr || pr === 'form')) return <ChatBookingDo key={state.read.read_id} route="form" readId={state.read.read_id} venue={venue} what={find.what} openAt={openAt} draft={draft} line={plan.line} />
            if (em && !callInstead && (!pr || pr === 'email')) return <ChatBookingDo key={state.read.read_id} route="email" readId={state.read.read_id} venue={venue} what={find.what} openAt={openAt} draft={draft} line={plan.line} />
            if (ph && (!pr || pr === 'call' || pr === 'call_email' || callInstead)) return <ChatBookingCall key={state.read.read_id} readId={state.read.read_id} country={state.read.country ?? find.country ?? null} phone={ph}
              venue={venue} draft={(callDraft ?? null) as never} whatText={find.what} openAt={openAt} onContacted={setContacted} line={callInstead ? null : plan.line} />
            if (ln) return <>{plan.line ? <div style={{ fontWeight: 600, marginBottom: 4 }}>{plan.line}</div> : null}
              <ChatBookingLink key={state.read.read_id} readId={state.read.read_id} platform={ln.value} draft={(find.draft ?? null) as never} openAt={openAt} /></>
            if (em) return <ChatBookingDo key={state.read.read_id} route="email" readId={state.read.read_id} venue={venue} what={find.what} openAt={openAt} draft={draft} line={plan.line} />
            if (wa) {
              const at = find.open_at ?? draft?.when?.at ?? ''
              const msg = `Hola, me gustaría reservar para ${draft?.how_many?.count ?? 2}${at ? ` el ${at.slice(8, 10)}/${at.slice(5, 7)} a las ${at.slice(11, 16)}` : ''}. ¿Tienen disponibilidad? Gracias.`
              return <div>{venue} books on WhatsApp — I&rsquo;ve written the message; you send it.{' '}
                <a className="price" href={`https://wa.me/${String(wa.value).replace(/\D/g, '')}?text=${encodeURIComponent(msg)}`} target="_blank" rel="noopener noreferrer">Open WhatsApp</a></div>
            }
            return <div>{plan.line ?? `I can't find a way to book ${venue} — no online booking, phone or email. Want me to try somewhere similar nearby?`}</div>
          })()}
        </div>
      )}
    </div>
  )
}
