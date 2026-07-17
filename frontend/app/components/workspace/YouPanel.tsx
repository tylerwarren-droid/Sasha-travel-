'use client'
import { useState, useEffect } from 'react'
import { User } from '@/types'
import { CURRENT_USER } from '@/lib/currentUser'
import { apiUrl, apiHeaders } from '@/lib/api'

interface YouPanelProps {
  user: User
  // Trips planned in this session — the profile is otherwise entirely historical.
  plannedThisSession?: number
  language?: string
}

interface BookedTrip {
  booking_ref: string
  title: string
  paid_at: string
  amount_usd: number
  days: number
  first_city: string
}

/** "2026-07-15T09:12:00" -> "July 2026". Falls back to the raw string if it won't parse. */
function monthYear(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso || ''
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English', vi: 'Tiếng Việt', ko: '한국어', zh: '中文',
  ja: '日本語', fr: 'Français', es: 'Español',
}

/**
 * The You tab: everything Sasha knows about the guest, in one place.
 *
 * This is the tab that earns trust — it's the visible proof that Sasha remembers, and the
 * place a guest checks when they wonder "why is she suggesting that?". So it shows the
 * reasoning inputs (preferences, who's travelling, where they've been), not just a name.
 */
export default function YouPanel({ user, plannedThisSession = 0, language = 'en' }: YouPanelProps) {
  const travellers = user.travellers ?? []
  const prefs = user.preferences ?? []

  // Trips the guest has actually paid for. This list used to be a hardcoded array, so it
  // showed the same two trips forever and a real booking never appeared. It now comes from
  // the bookings table — a trip lands here the moment Stripe confirms it.
  const [booked, setBooked] = useState<BookedTrip[]>([])
  const [loadingTrips, setLoadingTrips] = useState(true)
  useEffect(() => {
    let cancelled = false
    fetch(apiUrl('/api/trips'), { headers: apiHeaders() })
      .then(r => r.ok ? r.json() : Promise.reject(new Error(String(r.status))))
      .then(d => { if (!cancelled) setBooked(Array.isArray(d.trips) ? d.trips : []) })
      .catch(() => { if (!cancelled) setBooked([]) })
      .finally(() => { if (!cancelled) setLoadingTrips(false) })
    return () => { cancelled = true }
  }, [])

  // Seed history from the profile (trips taken before Sasha existed), then the real bookings.
  const seeded = (user.past_trips ?? []).map((t: any) => ({
    key: `seed-${t.title}`, when: t.return_date, title: t.title, sub: 'Travelled with Sasha', ref: '',
  }))
  const fromDb = booked.map(t => ({
    key: t.booking_ref,
    when: monthYear(t.paid_at),
    title: t.title,
    sub: [t.days ? `${t.days} day${t.days === 1 ? '' : 's'}` : '',
          t.amount_usd ? `$${Math.round(t.amount_usd).toLocaleString()}` : '']
      .filter(Boolean).join(' · ') || 'Booked with Sasha',
    ref: t.booking_ref,
  }))
  const trips = [...fromDb, ...seeded]

  const stats = [
    { k: 'Trips with Sasha', v: String(trips.length) },
    { k: 'Planned today', v: String(plannedThisSession) },
    { k: 'Party size', v: String(travellers.length || 1) },
  ]

  return (
    <div className="lw-stream">
      <div className="lw-who">
        <span className="lw-who-av">
          {(user.display_name || 'G').split(' ').map(w => w[0]).slice(0, 2).join('')}
        </span>
        <div className="lw-who-m">
          <div className="lw-who-n">{user.display_name}</div>
          <div className="lw-who-e">{user.email || CURRENT_USER.email}</div>
        </div>
        <span className="lw-who-tier">Member</span>
      </div>

      <div className="lw-stats">
        {stats.map(s => (
          <div className="lw-stat" key={s.k}>
            <span className="v">{s.v}</span>
            <span className="k">{s.k}</span>
          </div>
        ))}
      </div>

      <div className="lw-when">What Sasha remembers</div>
      <div className="lw-card">
        <div className="lw-cardBody" style={{ paddingTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {prefs.length > 0 ? (
            <div className="lw-prefchips">
              {prefs.map((p, i) => (
                <span className="lw-prefchip" key={i}>
                  <b>{p.key.split('.').slice(-1)[0].replace(/_/g, ' ')}</b>
                  {String(p.value).replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          ) : (
            <div className="lw-note-s">Nothing saved yet — tell Sasha how you like to travel and it'll appear here.</div>
          )}
          <div className="lw-note-s">Say “forget that” any time and Sasha drops a preference.</div>
        </div>
      </div>

      <div className="lw-when">Who's travelling</div>
      <div className="lw-card">
        <div className="lw-cardBody" style={{ paddingTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {travellers.map((t, i) => (
            <div className="lw-prefrow" key={i}>
              <span className="lw-prefv" style={{ textAlign: 'left', textTransform: 'none' }}>
                {t.relation === 'self' ? '🧑 ' : '🧑‍🤝‍🧑 '}{t.first_name}
              </span>
              <span className="lw-prefk">{t.relation === 'self' ? 'You' : t.relation}</span>
            </div>
          ))}
          <div className="lw-prefrow">
            <span className="lw-prefv" style={{ textAlign: 'left', textTransform: 'none' }}>🗣 Sasha speaks</span>
            <span className="lw-prefk">{LANGUAGE_NAMES[language] || language}</span>
          </div>
          <div className="lw-prefrow">
            <span className="lw-prefv" style={{ textAlign: 'left', textTransform: 'none' }}>💳 Prices shown in</span>
            <span className="lw-prefk">{user.default_currency || 'USD'}</span>
          </div>
        </div>
      </div>

      <div className="lw-when">Where you've been</div>
      <div className="lw-card">
        <div className="lw-cardBody" style={{ paddingTop: 14 }}>
          {loadingTrips && trips.length === 0 ? (
            <div className="lw-note-s">Loading your trips…</div>
          ) : trips.length === 0 ? (
            <div className="lw-note-s">No trips yet. Once you book one with Sasha, it'll live here.</div>
          ) : (
            <>
              <ol className="lw-past">
                {trips.map(t => (
                  <li key={t.key}>
                    <span className="yr">{t.when}</span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="pt">{t.title}</div>
                      <div className="ps">{t.sub}</div>
                    </div>
                    {t.ref ? <span className="lw-tripref">{t.ref}</span> : null}
                  </li>
                ))}
              </ol>
              <div className="lw-note-s" style={{ marginTop: 10 }}>
                Sasha won't re-pitch these unless you ask to go back.
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
