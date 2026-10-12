'use client'
/**
 * Sasha 248 · ONE PLACE CARD — the same card and the same detail sheet on /s2 and /next (WhatsApp gets the same content as text +
 * link, backend/agapi/venue_truth.text). One data shape: the search's card (its `place` from agapi/venue_truth) and, on tap, the
 * full place from /api/place/{id}. Every fact says where it came from: the venue's own site (quoted), or Google — a Google
 * category is never stated as what the place is (Sasha 250: not even labelled — only the venue's own words say what it is).
 * Tyler's S2 test (12 Oct): the thumbnails didn't open — a tap (or double-tap) on the photo or the card now opens the sheet.
 */
import { useEffect, useState } from 'react'
import { untag } from '@/lib/no-test-label.mjs'
import { cantRead, placeFacts, photoOf, sourceWord } from '@/lib/place-view.mjs'

type Ev = Record<string, any>   // eslint-disable-line @typescript-eslint/no-explicit-any
const GOLD = '#E8B923'
// Sasha 249 · the open sheet outlives a re-render: her turn re-rendering the cards (a new key → a remount) never closes the sheet
// they're reading. Cleared only when they close it (or open another).
let OPEN_SHEET: string | null = null

export function PlaceCard({ card: shown, onBook, tone = 'dark', badge }: { card: Ev; onBook: (name: string, placeId: string) => void; tone?: 'dark' | 'light'; badge?: string | null }) {
  const [open, setOpenNow] = useState(() => !!shown?.place_id && OPEN_SHEET === shown.place_id)
  const setOpen = (v: boolean) => {
    if (v) OPEN_SHEET = shown?.place_id ?? null
    else if (OPEN_SHEET === shown?.place_id) OPEN_SHEET = null
    setOpenNow(v)
  }
  // the venue engine's read of their site may land after the search (it's never waited for): the card asks once and updates
  const [fresh, setFresh] = useState<Ev | null>(null)
  useEffect(() => {
    if (!shown?.place_id || placeFacts(shown).type?.source === 'site') return
    let live = true
    fetch(`/api/place/${encodeURIComponent(shown.place_id)}`, { cache: 'no-store' }).then(r => r.json())
      .then(j => { if (live && j?.ok && j.place?.read === 'site') setFresh(j.place) }).catch(() => { /* the listing stays, labelled */ })
    return () => { live = false }
  }, [shown?.place_id])   // eslint-disable-line react-hooks/exhaustive-deps
  const card: Ev = fresh ? { ...shown, place: fresh, type: fresh.type?.value ?? shown.type, type_source: fresh.type?.source ?? shown.type_source } : shown
  const dim = tone === 'dark' ? 'rgba(255,255,255,.6)' : 'rgba(0,0,0,.6)'
  const photo = photoOf(card)
  const t = placeFacts(card).type
  return (
    <div data-place={card.place_id} style={{ minWidth: 230, maxWidth: 260, background: tone === 'dark' ? '#16151d' : '#fff', color: tone === 'dark' ? '#fff' : '#111',
      border: `1px solid ${tone === 'dark' ? 'rgba(255,255,255,.1)' : 'rgba(0,0,0,.12)'}`, borderRadius: 16, overflow: 'hidden', scrollSnapAlign: 'start' }}>
      <button type="button" aria-label={`Open ${untag(card.name)} — photos, site, hours and prices`} onClick={() => setOpen(true)} onDoubleClick={() => setOpen(true)}
        style={{ display: 'block', width: '100%', padding: 0, border: 0, background: 'transparent', cursor: 'pointer', textAlign: 'left', color: 'inherit' }}>
        {photo ? (
          <span style={{ display: 'block', position: 'relative' }}>
            {/* eslint-disable-next-line @next/next/no-img-element -- a remote venue photo (Google's short-lived URL, or the venue's own), sized by the card */}
            <img src={photo.url} alt="" referrerPolicy="no-referrer" style={{ width: '100%', height: 120, objectFit: 'cover', display: 'block' }} />
            <span style={{ position: 'absolute', right: 6, bottom: 6, fontSize: 10.5, padding: '1px 6px', borderRadius: 6, background: 'rgba(0,0,0,.55)', color: '#fff' }}>{photo.mark}</span>
          </span>
        ) : null}
        <span style={{ display: 'block', padding: '12px 12px 0' }}>
          {badge ? <span style={{ fontSize: 11, padding: '1px 6px', marginRight: 6, borderRadius: 8, background: GOLD, color: '#111' }}>{badge}</span> : null}
          <span style={{ fontWeight: 700 }}>{untag(card.name)}</span>
          {t ? <span style={{ display: 'block', fontSize: 13, color: dim, marginTop: 2 }}>{untag(t.value)}{t.source === 'site' ? ' · their site' : ''}</span> : null}
          <span style={{ display: 'block', fontSize: 13, color: dim, marginTop: 2 }}>
            {card.rating ? `★ ${card.rating}${card.rating_count ? ` (${Number(card.rating_count).toLocaleString()})` : ''}` : ''}{card.rating && card.area ? ' · ' : ''}{untag(card.area || '')}
          </span>
        </span>
      </button>
      <div style={{ padding: '8px 12px 12px', display: 'flex', gap: 8 }}>
        <button type="button" onClick={() => onBook(untag(card.name), card.place_id)} style={{ padding: '8px 14px', borderRadius: 999, border: `1px solid ${GOLD}`, background: GOLD, color: '#111', fontWeight: 700 }}>Book</button>
        <button type="button" onClick={() => setOpen(true)} style={{ padding: '8px 14px', borderRadius: 999, border: `1px solid ${GOLD}`, background: 'transparent', color: tone === 'dark' ? GOLD : '#7a5c00', fontWeight: 700 }}>Details</button>
      </div>
      {open ? <PlaceSheet card={card} onClose={() => setOpen(false)} onBook={() => { setOpen(false); onBook(untag(card.name), card.place_id) }} /> : null}
    </div>
  )
}

/** The detail sheet: photos, the venue's own site, hours, prices and what it is — each with its source — and Book. */
export function PlaceSheet({ card, onClose, onBook }: { card: Ev; onClose: () => void; onBook: () => void }) {
  const [place, setPlace] = useState<Ev>(card.place || card)
  const [reading, setReading] = useState(true)
  useEffect(() => {
    let live = true
    fetch(`/api/place/${encodeURIComponent(card.place_id)}`, { cache: 'no-store' }).then(r => r.json()).then(j => {
      if (live && j?.ok && j.place) setPlace(j.place)
    }).catch(() => { /* the card's own facts stay */ }).finally(() => { if (live) setReading(false) })
    return () => { live = false }
  }, [card.place_id])
  const f = placeFacts(place)
  // each photo marked by its own source: the venue's own first (photos_own of them), then Google's
  const own = typeof place.photos_own === 'number' ? place.photos_own : (place.photos_source === 'site' ? (place.photos || []).length : 0)
  const photos: { url: string; mark: string }[] = (place.photos || []).map((u: string, i: number) => ({ url: u, mark: i < own ? 'their site' : 'Google' }))
  const row = (label: string, x: Ev | null) => x && x.value ? (
    <div style={{ padding: '6px 0', borderTop: '1px solid rgba(255,255,255,.08)' }}>
      <div style={{ fontSize: 11.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'rgba(255,255,255,.55)' }}>{label}</div>
      <div style={{ fontSize: 15 }}>{untag(x.value)}</div>
      <div style={{ fontSize: 12, color: 'rgba(255,255,255,.55)' }}>{sourceWord(x)}{x.quote ? <> — &ldquo;{untag(x.quote)}&rdquo;</> : null}
        {x.source_url ? <> · <a href={x.source_url} target="_blank" rel="noreferrer" style={{ color: 'rgba(255,255,255,.7)' }}>page</a></> : null}</div>
    </div>) : null
  return (
    <div role="dialog" aria-modal="true" aria-label={`${untag(place.name || card.name)} — details`} onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(0,0,0,.6)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: 'min(560px, 100%)', maxHeight: '88vh', overflowY: 'auto', background: '#121119', color: '#fff',
        borderRadius: '18px 18px 0 0', padding: 16, boxShadow: '0 -8px 40px rgba(0,0,0,.5)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
          <div style={{ fontWeight: 800, fontSize: 18 }}>{untag(place.name || card.name)}</div>
          <button type="button" onClick={onClose} aria-label="Close" style={{ background: 'transparent', border: 0, color: '#fff', fontSize: 22, cursor: 'pointer' }}>×</button>
        </div>
        {photos.length ? (
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', margin: '10px 0' }}>
            {photos.map((p, i) => (
              <span key={i} style={{ position: 'relative', flex: '0 0 auto' }}>
                {/* eslint-disable-next-line @next/next/no-img-element -- the place's photos: Google's short-lived URLs or the venue's own */}
                <img src={p.url} alt="" referrerPolicy="no-referrer" style={{ height: 150, borderRadius: 10, display: 'block' }} />
                <span style={{ position: 'absolute', right: 6, bottom: 6, fontSize: 10.5, padding: '1px 6px', borderRadius: 6, background: 'rgba(0,0,0,.55)' }}>{p.mark}</span>
              </span>))}
          </div>) : null}
        {row('What it is', f.type)}
        {row('Hours', f.hours)}
        {row('Prices', f.price)}
        {place.rating ? <div style={{ padding: '6px 0', fontSize: 14, borderTop: '1px solid rgba(255,255,255,.08)' }}>★ {place.rating}{place.rating_count ? ` · ${Number(place.rating_count).toLocaleString()} reviews` : ''} <span style={{ color: 'rgba(255,255,255,.55)', fontSize: 12 }}>· Google</span></div> : null}
        {reading && place.read !== 'site' ? <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,.55)', padding: '6px 0' }}>Reading their own site…</div> : null}
        {cantRead(place) ? <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,.55)', padding: '6px 0' }}>Their site couldn&apos;t be read: {untag(cantRead(place))}</div> : null}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          <button type="button" onClick={onBook} style={{ padding: '10px 18px', borderRadius: 999, border: 0, background: GOLD, color: '#111', fontWeight: 800 }}>Book</button>
          {place.website ? <a href={place.website} target="_blank" rel="noreferrer" style={{ padding: '10px 16px', borderRadius: 999, border: `1px solid ${GOLD}`, color: GOLD, fontWeight: 700, textDecoration: 'none' }}>Their site ↗</a> : null}
          {place.listing_url ? <a href={place.listing_url} target="_blank" rel="noreferrer" style={{ padding: '10px 16px', borderRadius: 999, border: '1px solid rgba(255,255,255,.25)', color: '#fff', textDecoration: 'none' }}>Google Maps ↗</a> : null}
        </div>
      </div>
    </div>)
}
