'use client'
import { untagDeep } from '@/lib/no-test-label.mjs'   // Sasha 218
import { partySize } from '@/lib/trip-party.mjs'   // Sasha 246
import { useEffect, useState } from 'react'
import TripMap from '../TripMap'
import { bookingReq } from '@/lib/booking-client'
import type { RichItinerary } from '../ItineraryDays'

interface TripPanelProps {
  richItinerary: RichItinerary | null
  openDays: Set<number>
  toggleDay: (day: number) => void
  onBook?: () => void
  travellerCount: number
  // Nothing planned yet — send the guest to the Ideas tab rather than dead-ending them.
  onBrowseIdeas?: () => void
  onAsk?: (text: string) => void   // CR 50 · a sentence said to Sasha in the chat (the Move tab's "Getting there")
  // The confirmed booking reference, once the trip is paid for. Its presence turns every
  // booking control into a statement of what's already reserved: continuing to offer "Book"
  // on a paid trip invites the guest to buy the same rooms twice.
  // Sasha 249 · ONE STATUS: no longer read — the banner reads the server's trip_status (get_status's one source). Kept so
  // callers compile unchanged.
  bookingRef?: string | null
  // Set when the trip was PAID with the saved card in-conversation (Sasha asked, guest said
  // "use 1003"). The panel then says "Booked" and names the card; without it a ref means a
  // payment-free reservation and the wording stays "Reserved".
  paidWith?: { last4: string } | null
}

/**
 * The Trip tab: the plan Sasha built this session.
 *
 * Previously this rendered inside one long shared feed alongside preferences, past trips,
 * photos and the transcript, so the plan competed with everything else for attention. It now
 * owns a tab, with a sticky summary bar so the day count and total never scroll out of view.
 *
 * There is deliberately NO placeholder itinerary here. The old starter card ("7-Day Vietnam
 * Discovery", $6,480) was indistinguishable from a real plan, so when a build silently failed
 * the guest was left reading fake numbers and believing Sasha had planned their trip. An
 * honest empty state is better: it says nothing is planned, and points at the Ideas tab.
 */
/** Sasha 165 · THE ONE VIEW: the plan on the ACCOUNT (Postgres) with every booking slotted into its day — polled, so a
 *  booking made on WhatsApp shows here within seconds, and a plan made elsewhere (or before a reload) still shows. */
type ServerBooking = { id?: string; venue: string; time?: string; part?: string; status?: string; status_words?: string; replaces?: string; test?: boolean; edge?: string }
type ServerDay = { day: number; date?: string | null; city?: string; bookings?: ServerBooking[]; activities?: { name: string; time?: string; replaced_by?: string; added?: boolean }[]; stay?: { name?: string; state: string; words: string } }   // Sasha 198 R3 · the basket's stay (SASHA_BASKET=1)
const SHORT: Record<string, string> = { requested: 'Requested', attempting: 'Requested', pending: 'Not sent yet', confirmed: 'Confirmed ✅',
  guest_booked: 'Booked by you ✅', declined: 'Declined', quoted: 'Quoted — read their reply', proposed: 'They offered another time',
  unclear: 'Read their reply', link_sent: 'Link sent — not booked yet', waitlisted: 'Waiting list' }
/** a booking's status in a few words; its reference when confirmed (the full words are on its receipt) */
const shortStatus = (b: ServerBooking): string => {
  if (b.test && (b.status === 'confirmed' || b.status === 'guest_booked')) return 'Booked (demo)'   // Sasha 179 · never "Confirmed"; Sasha 218 · no TEST label
  const ref = /their ref ([A-Z0-9-]+)/.exec(b.status_words ?? '')
  return (SHORT[b.status ?? ''] ?? b.status_words ?? b.status ?? '') + (ref && b.status === 'confirmed' ? ` · ref ${ref[1]}` : '')
}
type ServerPlan = RichItinerary & { days: ServerDay[]; start?: string; trip_id?: string; trip_total?: TripTotal; trip_status?: TripStatus }
// Sasha 249 · ONE STATUS: what get_status says (agapi/s2_status.py) — the Trip banner's only source, never a client prop
type TripStatus = { state: string; line: string; refs: string[] }
const ON_IT = ['booked', 'partly_booked', 'awaiting_payment']
// Sasha 242 · ONE TOTAL: the basket's figure in euros, the same one Sasha says in the chat
type TripTotal = { total_eur: number; flights_eur: number; stays_eur: number; stays_are: string; trip_id: string }
const eur = (n: number) => `€${Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
type JRow = { id: string; venue: string; date: string | null; time: string | null; status: string; status_words?: string; booking_reference?: string | null; trip_id?: string }
/** CR 45 · a RelocateMe form on the Move tab: its state, its PDF one tap away (if there is one), where it goes next */
type JForm = { name: string; state: 'filled' | 'signed' | 'missing' | 'waiting' | 'done' | 'doing' | 'expired' | 'info'; note: string; pdf: string | null; next: string | null }
/** CR 50 · the Move tab's "Getting there": Sasha books the flights and first nights from here, onto this trip */
type JGetting = { title: string; text: string; say: string; entry_date?: string | null; to?: string }
type Journeys = { journeys: { key: string; label: string; title: string; start?: string | null; end?: string | null; count: number
    virtual?: boolean; extras?: JRow[]; forms?: JForm[]; getting_there?: JGetting }[]
  home: { label: string; items: JRow[] }; requests: JRow[]; receipts: JRow[]; everything: JRow[] }
/** Sasha 177 · the account's journeys and lists, polled like the plan (a booking made on WhatsApp shows within seconds) */
function useJourneys(): Journeys | null {
  const [j, setJ] = useState<Journeys | null>(null)
  useEffect(() => {
    let off = false
    const pull = async () => {
      const r = await bookingReq('/api/booking/journeys').catch(() => null)
      if (!off && r?.ok) setJ(untagDeep(r.json) as unknown as Journeys)   // Sasha 218 · no visible TEST label
    }
    pull()
    const t = setInterval(pull, 6000)
    window.addEventListener('sasha-plan-refresh', pull)   // Sasha 205 · /next's agent changed the trip: show it now, not in 6 s
    return () => { off = true; clearInterval(t); window.removeEventListener('sasha-plan-refresh', pull) }
  }, [])
  return j
}
const dayHead = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase()
function JourneyList({ title, rows }: { title: string; rows: JRow[] | null }) {
  if (!rows) return <div className="lw-note-s">Loading…</div>
  const byDay = new Map<string, JRow[]>()
  for (const r of rows) byDay.set(r.date ?? '', [...(byDay.get(r.date ?? '') ?? []), r])
  return (
    <>
      <div className="lw-when">{title}</div>
      <div className="lw-card"><div className="lw-cardBody" style={{ paddingTop: 14 }}>
        {rows.length === 0 && <div className="lw-note-s">Nothing here.</div>}
        {[...byDay].map(([d, rs]) => (
          <div key={d} style={{ marginBottom: 10 }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{d ? dayHead(d) : 'No day set yet'}</div>
            {rs.map((r) => (
              <div key={r.id} style={{ marginBottom: 6 }}>
                <div>{r.time ? `${r.time} · ` : ''}{r.venue.replace(/ \(TEST stand-in\)$/, '')}</div>
                <div className="lw-note-s">{r.status_words ?? r.status}{r.booking_reference ? ` · ref ${r.booking_reference}` : ''}</div>
              </div>
            ))}
          </div>
        ))}
      </div></div>
    </>
  )
}
const FORM_MARK: Record<JForm['state'], string> = { filled: '✓ Prepared — sign it', signed: '✓ Signed', missing: '☐ Still yours to do', waiting: '⏳ Waiting',
  done: '✓ Done', doing: '… Under way', expired: '⌛ Expired — fill it again', info: 'ℹ︎' }   // Sasha 184 · the health card's steps
function FormsList({ forms }: { forms: JForm[] }) {
  return (
    <>
      <div className="lw-when">Your forms — in the order you need them</div>
      <div className="lw-card"><div className="lw-cardBody" style={{ paddingTop: 14 }}>
        {forms.map((f) => (
          <div key={f.name} style={{ marginBottom: 8 }}>
            <div>{f.name} · <b>{FORM_MARK[f.state]}</b>{f.pdf ? <> · <a className="underline" href={f.pdf} target="_blank" rel="noopener noreferrer">Open the PDF</a></> : null}</div>
            <div className="lw-note-s">{f.note}{f.next ? ` — next: ${f.next}` : ''}</div>
          </div>
        ))}
      </div></div>
    </>
  )
}
type PlanRef = { trip_id: string; title: string; start?: string | null; end?: string | null; cities?: string[] }
function useServerPlan(tripId: string | null, onPlans?: (p: PlanRef[]) => void): ServerPlan | null {
  const [plan, setPlan] = useState<ServerPlan | null>(null)
  useEffect(() => {
    let off = false
    const pull = async () => {
      const r = await bookingReq(`/api/booking/plan${tripId ? `?trip_id=${encodeURIComponent(tripId)}` : ''}`).catch(() => null)
      if (!off && r?.ok) {
        const p = untagDeep(r.json.plan ?? null) as ServerPlan | null   // Sasha 218 · no visible TEST label
        setPlan(p ? { ...p, ...(r.json.trip_total ? { trip_total: r.json.trip_total as TripTotal } : {}),
                       ...(r.json.trip_status ? { trip_status: r.json.trip_status as TripStatus } : {}) } : p)   // Sasha 249 · + its status
        onPlans?.((r.json.plans ?? []) as PlanRef[])   // Sasha 175 · every trip on the account, for the picker
      }
    }
    pull()
    const t = setInterval(pull, 6000)
    window.addEventListener('sasha-plan-refresh', pull)   // Sasha 205 · /next's agent changed the trip: show it now, not in 6 s
    return () => { off = true; clearInterval(t); window.removeEventListener('sasha-plan-refresh', pull) }
  }, [tripId])  // eslint-disable-line react-hooks/exhaustive-deps
  return plan
}

export default function TripPanel({
  richItinerary: localItinerary, openDays, toggleDay, onBook, travellerCount, onBrowseIdeas, onAsk,
}: TripPanelProps) {
  // Sasha 175 · THE TABS the founder asked for: this trip (any of his trips), every booking anywhere, and what's still open
  // Sasha 177 · ONE TRIPS SPACE: a tab per journey (from /journeys), home, requests, receipts, everything. Switching tabs never
  // moves a booking — each is filed by the server into the journey whose dates AND place fit.
  const [view, setView] = useState<'trip' | 'home' | 'requests' | 'receipts' | 'everything'>('trip')
  const [tripId, setTripId] = useState<string | null>(null)
  const [, setPlans] = useState<PlanRef[]>([])
  const server = useServerPlan(tripId, setPlans)
  const jnLive = useJourneys()
  const [gone, setGone] = useState<string[]>([])   // Sasha 183 · a removed tab goes at once (the poll confirms it)
  const jn = jnLive ? { ...jnLive, journeys: jnLive.journeys.filter((t) => !gone.includes(t.key)) } : null
  const [handoff, setHandoff] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)
  const [removeSay, setRemoveSay] = useState<string | null>(null)
  // Sasha 183 · a removed plan never lingers as the chat's own copy (live: "Remove didn't remove"); a new plan shows again
  const [dropLocal, setDropLocal] = useState(false)
  useEffect(() => { setDropLocal(false) }, [localItinerary])
  const richItinerary = (tripId || dropLocal ? null : localItinerary) ?? (server as RichItinerary | null)
  const activeTrip = tripId ?? server?.trip_id ?? null
  const chip = (on: boolean) => (on ? { borderColor: '#E8B923', color: '#E8B923' } : undefined)
  const tabs = (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
      {(jn?.journeys ?? []).map((t) => (
        <span key={t.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
          <button className="lw-chip" style={chip(view === 'trip' && activeTrip === t.key)}
            onClick={() => {
              setTripId(t.key); setView('trip')
              // Sasha 195 · a product's tab opens its SPACE (its word, as if said) — the strict-space rule
              const sp = (t as { space?: string }).space
              if (sp) { try { window.dispatchEvent(new CustomEvent('sasha-open-space', { detail: sp })) } catch { /* the tab still shows its journey */ } }
            }}>{t.label}{t.count ? ` · ${t.count}` : ''}</button>
          {/* Sasha 181 (4) · ✕ removes a plan / a city's saved searches — one confirm, never a booking */}
          {(!t.virtual || t.key.startsWith('city:')) && (
            <button className="viewlink" aria-label={`Remove ${t.label}`} title="Remove this tab"
              onClick={() => { setRemoving(t.key); setRemoveSay(null) }} style={{ fontSize: 12, opacity: 0.6, padding: '0 4px' }}>✕</button>
          )}
        </span>
      ))}
      {removing && (() => {
        const t = (jn?.journeys ?? []).find((x) => x.key === removing)
        return (
          <div className="o2" style={{ width: '100%', fontSize: 13, marginTop: 4 }}>
            Remove “{t?.label ?? 'this tab'}”? {removing.startsWith('city:') ? 'Its saved searches go.' : 'The plan goes.'} Bookings in it are kept — they&rsquo;re cancelled separately.{' '}
            <button type="button" style={{ background: '#E8B923', color: '#111', border: 0, borderRadius: 8, padding: '4px 12px', fontWeight: 600, cursor: 'pointer', marginLeft: 6 }}
              onClick={async (e) => {
                e.stopPropagation()
                const key = removing
                const r = await bookingReq('/api/booking/journeys/remove', { key }).catch(() => null)
                setRemoveSay(String(r?.json?.say ?? 'Not removed — Sasha’s server did not answer.'))
                if (r?.ok && r.json?.ok && key) { setGone((g) => [...g, key]); if (activeTrip === key) { setTripId(null); setDropLocal(true) } setView('trip') }
                setRemoving(null)
              }}>Remove</button>
            <button type="button" style={{ background: 'transparent', color: 'inherit', border: '1px solid rgba(255,255,255,.35)', borderRadius: 8, padding: '4px 12px', cursor: 'pointer', marginLeft: 6 }}
              onClick={(e) => { e.stopPropagation(); setRemoving(null) }}>Keep it</button>
          </div>
        )
      })()}
      {removeSay && <div className="o2" style={{ width: '100%', fontSize: 13, marginTop: 4 }}>{removeSay}</div>}
      {(jn?.home.items.length ?? 0) > 0 && <button className="lw-chip" style={chip(view === 'home')} onClick={() => setView('home')}>{jn?.home.label ?? 'Home'} · {jn!.home.items.length}</button>}{/* Sasha 181 · no empty home tab */}
      <button className="lw-chip" style={chip(view === 'requests')} onClick={() => setView('requests')}>Requests{jn?.requests.length ? ` · ${jn.requests.length}` : ''}</button>
      <button className="lw-chip" style={chip(view === 'receipts')} onClick={() => setView('receipts')}>Receipts</button>
      <button className="lw-chip" style={chip(view === 'everything')} onClick={() => setView('everything')}>Everything</button>
    </div>
  )
  const curJ = (jn?.journeys ?? []).find((t) => t.key === activeTrip)
  const getting = curJ?.getting_there
  const formsHere = curJ?.forms?.length ? (
    <>
      {getting && (
        <>
          <div className="lw-when">✈️ {getting.title}</div>
          <div className="lw-card"><div className="lw-cardBody" style={{ paddingTop: 14 }}>
            <div>{getting.text}</div>
            {onAsk && <button className="lw-empty-cta" style={{ marginTop: 10 }} onClick={() => onAsk(getting.say)}>Ask Sasha to book it →</button>}
          </div></div>
        </>
      )}
      <FormsList forms={curJ.forms} />
    </>
  ) : null   // CR 45 · every form lives in the journey; CR 50 · and how to get there
  if (view === 'trip' && curJ?.virtual) return <div className="lw-trip">{tabs}{formsHere}<JourneyList title={curJ.title} rows={curJ.extras ?? []} /></div>
  const alsoHere = curJ?.extras?.length ? <JourneyList title={`Also on this journey (from ${curJ.title.match(/campus/i) ? 'CampusMe' : 'RelocateMe'})`} rows={curJ.extras} /> : null
  if (view !== 'trip') {
    const rows = !jn ? null : view === 'home' ? jn.home.items : view === 'requests' ? jn.requests : view === 'receipts' ? jn.receipts : jn.everything
    const title = view === 'home' ? `${jn?.home.label ?? 'Home'} — outside any trip` : view === 'requests' ? 'Waiting on a reply'
      : view === 'receipts' ? 'Booked' : 'Everything, by date'
    return <div className="lw-trip">{tabs}<JourneyList title={title} rows={rows} /></div>
  }
  const serverDay = (n: number): ServerDay | undefined => (server?.days ?? []).find((x) => x.day === n)
  // Sasha 249 · ONE STATUS (EU 245 §1.12): the banner said "✓ Paid … · not booked yet" from a client bookingRef prop. It now says
  // the server's status line for THIS trip — the same words as get_status in the chat, the /s2 card and the WhatsApp line
  const ts = server?.trip_status ?? null   // the server's plan and its status are for the same trip (/api/booking/plan)
  const isBooked = Boolean(ts && ON_IT.includes(ts.state))
  const doneWord = ts?.state === 'awaiting_payment' ? 'Waiting for payment' : ts?.state === 'partly_booked' ? 'Partly booked' : 'Booked'
  if (!richItinerary) {
    return (
      <div className="lw-stream">
        {tabs}
        <div className="lw-empty">
          <div className="lw-empty-ic">🗺</div>
          <div className="lw-empty-t">No trip planned yet</div>
          <div className="lw-empty-s">
            Tell Sasha where you'd like to go and she'll build the day-by-day plan here — or start
            from one of her ideas.
          </div>
          <button className="lw-empty-cta" onClick={onBrowseIdeas}>Browse Sasha's ideas →</button>
        </div>
      </div>
    )
  }

  // Sasha 242 · the basket's euro total for THIS trip wins over the planner's dollar estimate (they disagreed: €496 vs $340 hotels)
  const tt = server?.trip_total && server.trip_total.trip_id === (activeTrip ?? server.trip_id) ? server.trip_total : null
  const cb: any = tt ? null : (richItinerary as any).cost_breakdown
  const pax = partySize(richItinerary, cb, cb?.travellers || travellerCount)   // Sasha 246 · the trip's own party first
  const dayCount = richItinerary.days?.length || 0
  // Where the trip actually begins — the first day that names a city, not necessarily day 1.
  const arrivalCity = (richItinerary.days || []).find((d: any) => d.city)?.city || ''
  // Distinct overnight stays across the trip — a day without its own hotel continues the
  // previous night's stay, so count unique names rather than days.
  const stayCount = new Set(
    (richItinerary.days || []).map((d: any) => d.hotel?.name).filter(Boolean)
  ).size

  return (
    <>
      {tabs}
      {formsHere}
      {alsoHere}
      <div className="lw-summary">
        <div className="lw-sumcell"><span className="k">Days</span><span className="v">{dayCount}</span></div>
        <div className="lw-sumcell"><span className="k">Travellers</span><span className="v">{pax}</span></div>
        {stayCount > 0 && (
          <div className="lw-sumcell"><span className="k">Stays</span><span className="v">{stayCount}</span></div>
        )}
        <div className="lw-sumcell tot">
          <span className="k">{isBooked ? 'Trip total' : tt ? 'All in' : 'Estimated total'}</span>
          <span className="amt">{tt ? eur(tt.total_eur) : `$${(richItinerary.estimated_total_usd || 0).toLocaleString()}`}</span>
        </div>
      </div>

      <div className="lw-stream">
        <div className="lw-card fresh">
          <div className="lw-cardHd">
            <span className="lw-ci gold">🗺</span>
            <div className="lw-meta">
              <div className="lw-k">Your itinerary</div>
              <div className="lw-h">{richItinerary.title}</div>
              {/* Sasha 165 · hand-off: ONE WhatsApp, "Picking up: <trip> — <the open item>. Reply to carry on." */}
              <button type="button" className="lw-handoff" onClick={async () => {
                setHandoff('Sending…')
                const r = await bookingReq('/api/booking/handoff/phone', {}).catch(() => null)
                setHandoff(String(r?.json?.say ?? 'Not sent — try again.'))
              }}>📱 Continue on my phone</button>
              {handoff && <div style={{ fontSize: 11.5, opacity: 0.75, marginTop: 2 }}>{handoff}</div>}
            </div>
          </div>
          <div className="lw-cardBody">
          <div className="lw-trip-cols">
          <div className="lw-trip-left">
            {richItinerary.summary && <div className="lw-day-desc" style={{ marginBottom: 4 }}>{richItinerary.summary}</div>}
            {/* Only offer flights to a city the plan actually starts in. This used to fall
                back to a hardcoded 'Hanoi', so a trip beginning anywhere else (or with day 1
                missing a city) advertised — and deep-linked to — flights to the wrong side of
                the country. If we don't know the arrival city, we don't guess one. */}
            {/* Flights book IN-APP through Sasha's flight cards — no Google Flights
                deep-link. This hint keeps the guest inside the conversation. */}
            {arrivalCity && (
              <div className="lw-flights">
                <span className="lw-flights-ic">✈️</span>
                <div className="lw-flights-meta">
                  <div className="lw-flights-k">Getting there</div>
                  <div className="lw-flights-h">Ask Sasha for flights to {arrivalCity} — book right here</div>
                </div>
              </div>
            )}
            <div className="lw-mapwrap"><TripMap days={richItinerary.days} /></div>


            {tt && (
              <div className="lw-breakdown">
                <span>✈️ Flights {eur(tt.flights_eur)}</span>
                <span>🏨 Stays {eur(tt.stays_eur)}{tt.stays_are === 'estimates' ? ' (estimate)' : ''}</span>
              </div>
            )}
            {cb && (
              <div className="lw-breakdown">
                <span>🏨 Hotels ${Number(cb.hotels || 0).toLocaleString()}</span>
                <span>🎟️ Experiences ${Number(cb.experiences || 0).toLocaleString()}</span>
                <span>🍜 Meals ${Number(cb.meals || 0).toLocaleString()}</span>
                <span>🚐 Transfers ${Number(cb.transport || 0).toLocaleString()}</span>
              </div>
            )}
            {isBooked ? (
              <>
                <div className="lw-bookedBanner">{ts!.line}</div>
                {ts!.refs.length > 0 && <div className="lw-booknote">Keep your reference{ts!.refs.length > 1 ? 's' : ''} for your records: {ts!.refs.join(', ')}.</div>}
              </>
            ) : (
              <>
                {/* Sasha 179 (1) · the old button charged a demo "saved card" that doesn't exist. The real route: "book it" in the
                    chat → the TEST read-back of what can actually be booked → one TEST payment on the phone. */}
                <div className="lw-booknote">To book this trip, say “book it” in the chat: Sasha reads back the hotels and flights that can be booked, then sends one payment to your phone — nothing is charged.</div>
              </>
            )}
          </div>
          <div className="lw-trip-right">
            <div className="lw-when" style={{ marginTop: 0 }}>Day by day</div>
            {/* Sasha 198 R10 · the trip's flights, from the basket, each in its state's words (Pacioli's line once booked) */}
            {(((server as any)?.basket?.flights ?? []) as { owner?: string; flights?: string; from?: string; to?: string; words: string; state: string }[]).map((f, fi) => (
              <div key={`bf${fi}`} className="lw-day-city" style={{ color: f.state === 'booked' ? '#7ee2a8' : f.state === 'cancelled' || f.state === 'failed' ? '#f19999' : '#E8B923' }}>
                ✈️ {f.state === 'booked' || f.state === 'failed' || f.state === 'cancelled' ? f.words : `${f.owner ?? ''} ${f.flights ?? ''} ${f.from ?? ''}→${f.to ?? ''} — ${f.words}`}
              </div>
            ))}
            {(() => {
              let carried: any = null
              return richItinerary.days?.map(d => {
                const hotel: any = d.hotel && (d.hotel as any).name ? d.hotel : null
                if (hotel) carried = hotel
                const showHotel: any = hotel || carried
                const continuing = !hotel && !!carried
                const isOpen = openDays.has(d.day)
                return (
                  <div className={`lw-day ${isOpen ? 'open' : ''}`} key={d.day}>
                    <button className="lw-day-hd" onClick={() => toggleDay(d.day)} aria-expanded={isOpen}>
                      <div className="num">{d.day}</div>
                      <div className="lw-day-meta">
                        <div className="lw-day-title">{d.title}</div>
                        <div className="lw-day-city">📍 {d.city}{showHotel ? ` · ${showHotel.name}` : ''}{serverDay(d.day)?.date
                          ? ` · ${new Date(`${serverDay(d.day)!.date}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' })}` : ''}</div>
                        {/* Sasha 165 · this day's bookings, with their status — shown even when the day is folded */}
                        {(serverDay(d.day)?.bookings ?? []).map((b, bi) => (
                          <div key={bi} className="lw-day-city" style={{ color: /Confirmed|Booked/i.test(b.status_words ?? '') ? '#7ee2a8' : /Declined/i.test(b.status_words ?? '') ? '#f19999' : '#E8B923' }}>
                            🔖 {b.time ? `${b.time}${b.edge ? ` (${b.edge})` : ''} · ` : ''}{b.venue} — {shortStatus(b)}
                          </div>
                        ))}
                        {/* Sasha 167 · a place picked on WhatsApp, on its day — a plan, not a booking */}
                        {(serverDay(d.day)?.activities ?? []).filter((a) => a.added && !a.replaced_by).map((a, ai) => (
                          <div key={`a${ai}`} className="lw-day-city">📍 {a.time ? `${a.time} · ` : ''}{a.name} — not booked yet</div>
                        ))}
                      </div>
                      <div className="lw-day-right">
                        <span className="lw-day-tag">Day {d.day}</span>
                        <span className={`lw-chev ${isOpen ? 'open' : ''}`}>⌄</span>
                      </div>
                    </button>

                    {isOpen && (
                      <div className="lw-day-detail">
                        {d.image && (
                          <div className="lw-day-imgwrap">
                            <img className="lw-day-img" src={d.image} alt={d.title} loading="lazy" />
                          </div>
                        )}
                        {d.description && <div className="lw-day-desc">{d.description}</div>}

                        {d.activities && d.activities.length > 0 && (
                          <div className="lw-acts">
                            {/* Plain rows — activities book through Sasha's Book & Pay
                                cards, never a GetYourGuide link. */}
                            {d.activities.map((a: any, ai: number) => (
                              (serverDay(d.day)?.activities ?? []).some((x) => x.name === a.name && x.replaced_by) ? null :
                              <div className="lw-act" key={ai}>
                                <span className="lw-act-time">{a.time}</span>
                                <div className="lw-act-body">
                                  <div className="lw-act-name">{a.name}</div>
                                  {a.blurb && <div className="lw-act-blurb">{a.blurb}</div>}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {showHotel && (
                          <div className="lw-hotel">
                            <span className="lw-hotel-ic">🏨</span>
                            <div className="lw-hotel-meta">
                              <div className="lw-hotel-k">{continuing ? 'Continuing your stay' : 'Overnight'}</div>
                              <div className="lw-hotel-name">{showHotel.name}</div>
                              {showHotel.rating && (
                                (showHotel as { source?: string }).source === 'google'   /* Sasha 211 · Google's own 1–5 rating, as its listing says */
                                  ? <div className="lw-hotel-rating">★ {showHotel.rating} · {(showHotel.reviews ?? 0).toLocaleString()} Google reviews</div>
                                  : <div className="lw-hotel-rating">★ {showHotel.rating}/10 · {(showHotel.reviews ?? 0).toLocaleString()} reviews{showHotel.tag ? ` · ${showHotel.tag}` : ''}</div>
                              )}
                              {(showHotel as { price_label?: string }).price_label ? (   /* Sasha 211 · an ESTIMATE, labelled as one */
                                <div className="lw-hotel-price">{(showHotel as { price_label?: string }).price_label}{continuing ? ' · same stay' : ''}</div>
                              ) : showHotel.price_from ? (
                                <div className="lw-hotel-price">${Number(showHotel.price_from).toLocaleString()}/night{continuing ? ' · same stay' : ''}</div>
                              ) : null}
                            </div>
                            {/* Stays are paid inside the whole-trip checkout — never a
                                Booking.com button. */}
                            {serverDay(d.day)?.stay
                              ? <span className="lw-hotel-reserved" style={serverDay(d.day)!.stay!.state === 'booked' ? undefined : { opacity: 0.75 }}>{serverDay(d.day)!.stay!.words}</span>
                              : isBooked
                              ? <span className="lw-hotel-reserved">✓ {doneWord}</span>
                              : <span className="lw-hotel-reserved" style={{ opacity: 0.75 }}>Included in trip</span>}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })
            })()}
          </div>
          </div>
          </div>
        </div>
      </div>
    </>
  )
}
