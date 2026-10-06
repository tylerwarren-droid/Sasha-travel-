'use client'
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
  // The confirmed booking reference, once the trip is paid for. Its presence turns every
  // booking control into a statement of what's already reserved: continuing to offer "Book"
  // on a paid trip invites the guest to buy the same rooms twice.
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
type ServerDay = { day: number; date?: string | null; city?: string; bookings?: ServerBooking[]; activities?: { name: string; time?: string; replaced_by?: string; added?: boolean }[] }
const SHORT: Record<string, string> = { requested: 'Requested', attempting: 'Requested', pending: 'Not sent yet', confirmed: 'Confirmed ✅',
  guest_booked: 'Booked by you ✅', declined: 'Declined', quoted: 'Quoted — read their reply', proposed: 'They offered another time',
  unclear: 'Read their reply', link_sent: 'Link sent — not booked yet', waitlisted: 'Waiting list' }
/** a booking's status in a few words; its reference when confirmed (the full words are on its receipt) */
const shortStatus = (b: ServerBooking): string => {
  const ref = /their ref ([A-Z0-9-]+)/.exec(b.status_words ?? '')
  return (SHORT[b.status ?? ''] ?? b.status_words ?? b.status ?? '') + (ref && b.status === 'confirmed' ? ` · ref ${ref[1]}` : '')
}
type ServerPlan = RichItinerary & { days: ServerDay[]; start?: string; trip_id?: string }
type JRow = { id: string; venue: string; date: string | null; time: string | null; status: string; status_words?: string; booking_reference?: string | null; trip_id?: string }
type Journeys = { journeys: { key: string; label: string; title: string; start?: string | null; end?: string | null; count: number
    virtual?: boolean; extras?: JRow[] }[]
  home: { label: string; items: JRow[] }; requests: JRow[]; receipts: JRow[]; everything: JRow[] }
/** Sasha 177 · the account's journeys and lists, polled like the plan (a booking made on WhatsApp shows within seconds) */
function useJourneys(): Journeys | null {
  const [j, setJ] = useState<Journeys | null>(null)
  useEffect(() => {
    let off = false
    const pull = async () => {
      const r = await bookingReq('/api/booking/journeys').catch(() => null)
      if (!off && r?.ok) setJ(r.json as unknown as Journeys)
    }
    pull()
    const t = setInterval(pull, 6000)
    return () => { off = true; clearInterval(t) }
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
                <div>{r.time ? `${r.time} · ` : ''}{r.venue.replace(/ \(TEST stand-in\)$/, ' (test venue stood in)')}</div>
                <div className="lw-note-s">{r.status_words ?? r.status}{r.booking_reference ? ` · ref ${r.booking_reference}` : ''}</div>
              </div>
            ))}
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
        setPlan((r.json.plan ?? null) as ServerPlan | null)
        onPlans?.((r.json.plans ?? []) as PlanRef[])   // Sasha 175 · every trip on the account, for the picker
      }
    }
    pull()
    const t = setInterval(pull, 6000)
    return () => { off = true; clearInterval(t) }
  }, [tripId])  // eslint-disable-line react-hooks/exhaustive-deps
  return plan
}

export default function TripPanel({
  richItinerary: localItinerary, openDays, toggleDay, onBook, travellerCount, onBrowseIdeas, bookingRef, paidWith,
}: TripPanelProps) {
  // Sasha 175 · THE TABS the founder asked for: this trip (any of his trips), every booking anywhere, and what's still open
  // Sasha 177 · ONE TRIPS SPACE: a tab per journey (from /journeys), home, requests, receipts, everything. Switching tabs never
  // moves a booking — each is filed by the server into the journey whose dates AND place fit.
  const [view, setView] = useState<'trip' | 'home' | 'requests' | 'receipts' | 'everything'>('trip')
  const [tripId, setTripId] = useState<string | null>(null)
  const [, setPlans] = useState<PlanRef[]>([])
  const server = useServerPlan(tripId, setPlans)
  const jn = useJourneys()
  const [handoff, setHandoff] = useState<string | null>(null)
  const richItinerary = (tripId ? null : localItinerary) ?? (server as RichItinerary | null)
  const activeTrip = tripId ?? server?.trip_id ?? null
  const chip = (on: boolean) => (on ? { borderColor: '#E8B923', color: '#E8B923' } : undefined)
  const tabs = (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
      {(jn?.journeys ?? []).map((t) => (
        <button key={t.key} className="lw-chip" style={chip(view === 'trip' && activeTrip === t.key)}
          onClick={() => { setTripId(t.key); setView('trip') }}>{t.label}{t.count ? ` · ${t.count}` : ''}</button>
      ))}
      <button className="lw-chip" style={chip(view === 'home')} onClick={() => setView('home')}>{jn?.home.label ?? 'Home'}{jn?.home.items.length ? ` · ${jn.home.items.length}` : ''}</button>
      <button className="lw-chip" style={chip(view === 'requests')} onClick={() => setView('requests')}>Requests{jn?.requests.length ? ` · ${jn.requests.length}` : ''}</button>
      <button className="lw-chip" style={chip(view === 'receipts')} onClick={() => setView('receipts')}>Receipts</button>
      <button className="lw-chip" style={chip(view === 'everything')} onClick={() => setView('everything')}>Everything</button>
    </div>
  )
  const curJ = (jn?.journeys ?? []).find((t) => t.key === activeTrip)
  if (view === 'trip' && curJ?.virtual) return <div className="lw-trip">{tabs}<JourneyList title={curJ.title} rows={curJ.extras ?? []} /></div>
  const alsoHere = curJ?.extras?.length ? <JourneyList title={`Also on this journey (from ${curJ.title.match(/campus/i) ? 'CampusMe' : 'RelocateMe'})`} rows={curJ.extras} /> : null
  if (view !== 'trip') {
    const rows = !jn ? null : view === 'home' ? jn.home.items : view === 'requests' ? jn.requests : view === 'receipts' ? jn.receipts : jn.everything
    const title = view === 'home' ? `${jn?.home.label ?? 'Home'} — outside any trip` : view === 'requests' ? 'Waiting on a reply'
      : view === 'receipts' ? 'Booked' : 'Everything, by date'
    return <div className="lw-trip">{tabs}<JourneyList title={title} rows={rows} /></div>
  }
  const serverDay = (n: number): ServerDay | undefined => (server?.days ?? []).find((x) => x.day === n)
  const isBooked = Boolean(bookingRef)
  const isPaid = isBooked && Boolean(paidWith)
  const doneWord = isPaid ? 'Paid' : 'Saved'   // Sasha 133 · nobody was contacted on this path: never "Booked"/"Reserved"
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

  const cb: any = (richItinerary as any).cost_breakdown
  const pax = cb?.travellers || travellerCount
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
      {alsoHere}
      <div className="lw-summary">
        <div className="lw-sumcell"><span className="k">Days</span><span className="v">{dayCount}</span></div>
        <div className="lw-sumcell"><span className="k">Travellers</span><span className="v">{pax}</span></div>
        {stayCount > 0 && (
          <div className="lw-sumcell"><span className="k">Stays</span><span className="v">{stayCount}</span></div>
        )}
        <div className="lw-sumcell tot">
          <span className="k">{isBooked ? 'Trip total' : 'Estimated total'}</span>
          <span className="amt">${(richItinerary.estimated_total_usd || 0).toLocaleString()}</span>
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
                <div className="lw-bookedBanner">✓ {doneWord}{isPaid && paidWith!.last4 ? ` with card ending ${paidWith!.last4}` : ''} · not booked yet · Ref {bookingRef}</div>
                <div className="lw-booknote">{isPaid ? 'Everything above is booked and paid.' : 'Everything above is reserved.'} Keep your reference for your records.</div>
              </>
            ) : (
              <>
                <button className="lw-bookBtn" onClick={onBook}>Book the whole trip with Sasha →</button>
                <div className="lw-booknote">Tap here or just say “book it” — Sasha will confirm your saved card and complete the booking right here.</div>
              </>
            )}
          </div>
          <div className="lw-trip-right">
            <div className="lw-when" style={{ marginTop: 0 }}>Day by day</div>
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
                            🔖 {b.time ? `${b.time}${b.edge ? ` (${b.edge})` : ''} · ` : ''}{b.test ? 'TEST · ' : ''}{b.venue} — {shortStatus(b)}
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
                                <div className="lw-hotel-rating">★ {showHotel.rating}/10 · {(showHotel.reviews ?? 0).toLocaleString()} reviews{showHotel.tag ? ` · ${showHotel.tag}` : ''}</div>
                              )}
                              {showHotel.price_from ? (
                                <div className="lw-hotel-price">${Number(showHotel.price_from).toLocaleString()}/night{continuing ? ' · same stay' : ''}</div>
                              ) : null}
                            </div>
                            {/* Stays are paid inside the whole-trip checkout — never a
                                Booking.com button. */}
                            {isBooked
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
