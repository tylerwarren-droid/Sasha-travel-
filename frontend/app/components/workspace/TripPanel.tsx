'use client'
import TripMap from '../TripMap'
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
export default function TripPanel({
  richItinerary, openDays, toggleDay, onBook, travellerCount, onBrowseIdeas, bookingRef,
}: TripPanelProps) {
  const isBooked = Boolean(bookingRef)
  if (!richItinerary) {
    return (
      <div className="lw-stream">
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
            </div>
          </div>
          <div className="lw-cardBody">
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
                        <div className="lw-day-city">📍 {d.city}{showHotel ? ` · ${showHotel.name}` : ''}</div>
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
                              ? <span className="lw-hotel-reserved">✓ Reserved</span>
                              : <span className="lw-hotel-reserved" style={{ opacity: 0.75 }}>Included in trip</span>}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })
            })()}

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
                <div className="lw-bookedBanner">✓ Reserved · Ref {bookingRef}</div>
                <div className="lw-booknote">Everything above is reserved. Keep your reference for your records.</div>
              </>
            ) : (
              <>
                <button className="lw-bookBtn" onClick={onBook}>Reserve the whole trip with Sasha →</button>
                <div className="lw-booknote">No payment needed — just say “book it” and Sasha takes the reservation.</div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
