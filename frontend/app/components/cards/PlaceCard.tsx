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
import { report } from '@/lib/mic-state'   // Sasha 274 · a card that arrived without its content says so (its keys only, never a value)

type Ev = Record<string, any>   // eslint-disable-line @typescript-eslint/no-explicit-any
const GOLD = '#E8B923'
// Sasha 249 · the open sheet outlives a re-render: her turn re-rendering the cards (a new key → a remount) never closes the sheet
// they're reading. Cleared only when they close it (or open another).
let OPEN_SHEET: string | null = null

/** Sasha 276 · what AgAPI venue.discover says on a card (its words, never Sasha's): feel, price level, distance, availability, how far
 *  Sasha can take it, the pick's reason, and the photo's credit. All optional: /next's cards are unchanged without them. */
export type CardExtra = { feel?: string | null; price_level?: number | null; distance_m?: number | null; availability_words?: string | null
  how_far_words?: string | null; reason?: string | null; photo_by?: string | null
  label?: string | null   // Sasha 291 · AgAPI's own label for what they want to do (a walk-in place, for takeaway or eat now)
  recognition?: string | null   // Sasha 292 · AgAPI's recognition sentence, as given (credited and dated) — none → nothing
  sources_url?: string | null }   // Sasha 293 · CR 125 · AgAPI's "Our sources" page, when its answer carries one

export function PlaceCard({ card: shown, onBook, tone = 'dark', badge, extra, action, noDetails }: { card: Ev; onBook: (name: string, placeId: string) => void; tone?: 'dark' | 'light'; badge?: string | null
  extra?: CardExtra; action?: { label: string; onClick: () => void }; noDetails?: boolean }) {
  const [open, setOpenNow] = useState(() => !!shown?.place_id && OPEN_SHEET === shown.place_id)
  const setOpen = (v: boolean) => {
    if (v) OPEN_SHEET = shown?.place_id ?? null
    else if (OPEN_SHEET === shown?.place_id) OPEN_SHEET = null
    setOpenNow(v)
  }
  // the venue engine's read of their site may land after the search (it's never waited for): the card asks once and updates
  const [fresh, setFresh] = useState<Ev | null>(null)
  useEffect(() => {
    if (noDetails || !shown?.place_id || placeFacts(shown).type?.source === 'site') return   // 276: a marketplace is never read
    let live = true
    fetch(`/api/place/${encodeURIComponent(shown.place_id)}`, { cache: 'no-store' }).then(r => r.json())
      .then(j => { if (live && j?.ok && j.place?.read === 'site') setFresh(j.place) }).catch(() => { /* the listing stays, labelled */ })
    return () => { live = false }
  }, [shown?.place_id])   // eslint-disable-line react-hooks/exhaustive-deps
  const card: Ev = fresh ? { ...shown, place: fresh, type: fresh.type?.value ?? shown.type, type_source: fresh.type?.source ?? shown.type_source } : shown
  // Sasha 274 · item 2 (row 1061, Tyler's iPhone 14:48: two cards as EMPTY dark boxes): a card is its content — the name and details
  // at once, the photo streaming in after (a photo that fails is never left as a dark box). No name → no card, and it is reported.
  const [photoOk, setPhotoOk] = useState(true)
  const named = typeof card?.name === 'string' && !!untag(card.name).trim()
  useEffect(() => { if (!named) report('card_empty', { why: Object.keys(shown || {}).slice(0, 12).join(',') || typeof shown }) }, [named])   // eslint-disable-line react-hooks/exhaustive-deps
  const dim = tone === 'dark' ? 'rgba(255,255,255,.6)' : 'rgba(0,0,0,.6)'
  const photo = photoOk ? (extra?.photo_by && card.photo ? { url: String(card.photo), mark: String(extra.photo_by) } : photoOf(card)) : null   // 276: the photo's own credit
  const t = placeFacts(card).type
  if (!named) return null
  return (
    <div data-place={card.place_id} style={{ minWidth: 230, maxWidth: 260, background: tone === 'dark' ? '#16151d' : '#fff', color: tone === 'dark' ? '#fff' : '#111',
      border: `1px solid ${tone === 'dark' ? 'rgba(255,255,255,.1)' : 'rgba(0,0,0,.12)'}`, borderRadius: 16, overflow: 'hidden', scrollSnapAlign: 'start',
      isolation: 'isolate', transform: 'translateZ(0)', flex: 'none' }}>{/* Sasha 274 · its own layer: WebKit never leaves a rounded, clipped card in a scrolling row unpainted */}
      <button type="button" aria-label={`Open ${untag(card.name)} — photos, site, hours and prices`} onClick={() => { if (!noDetails) setOpen(true) }} onDoubleClick={() => { if (!noDetails) setOpen(true) }}
        style={{ display: 'block', width: '100%', padding: 0, border: 0, background: 'transparent', cursor: 'pointer', textAlign: 'left', color: 'inherit' }}>
        {photo ? (
          <span style={{ display: 'block', position: 'relative' }}>
            {/* eslint-disable-next-line @next/next/no-img-element -- a remote venue photo (Google's short-lived URL, or the venue's own), sized by the card */}
            <img src={photo.url} alt="" referrerPolicy="no-referrer" loading="lazy" onError={() => { setPhotoOk(false); report('card_photo_failed', { why: photo.mark }) }} style={{ width: '100%', height: 120, objectFit: 'cover', display: 'block' }} />
            <span style={{ position: 'absolute', right: 6, bottom: 6, fontSize: 10.5, padding: '1px 6px', borderRadius: 6, background: 'rgba(0,0,0,.55)', color: '#fff' }}>{photo.mark}</span>
          </span>
        ) : null}
        <span style={{ display: 'block', padding: '12px 12px 0' }}>
          {badge ? <span style={{ fontSize: 11, padding: '1px 6px', marginRight: 6, borderRadius: 8, background: GOLD, color: '#111' }}>{badge}</span> : null}
          <span style={{ fontWeight: 700 }}>{untag(card.name)}</span>
          {t ? <span style={{ display: 'block', fontSize: 13, color: dim, marginTop: 2 }}>{untag(t.value)}{t.source === 'site' ? ' · their site' : ''}</span> : null}
          <span style={{ display: 'block', fontSize: 13, color: dim, marginTop: 2 }}>
            {card.rating ? `★ ${card.rating}${card.rating_count ? ` (${Number(card.rating_count).toLocaleString()})` : ''}` : ''}{card.rating && card.area ? ' · ' : ''}{untag(card.area || '')}
            {extra?.price_level ? `${card.rating || card.area ? ' · ' : ''}${'€'.repeat(Math.max(1, Math.min(4, Number(extra.price_level))))}` : ''}
            {typeof extra?.distance_m === 'number' ? ` · ${extra.distance_m < 1000 ? `${Math.round(extra.distance_m)} m` : `${(extra.distance_m / 1000).toFixed(1)} km`}` : ''}
          </span>
          {extra?.feel ? <span style={{ display: 'block', fontSize: 13, color: dim, marginTop: 2 }}>{untag(extra.feel)}</span> : null}
          {extra?.recognition ? <span data-recognition style={{ display: 'block', fontSize: 11.5, color: GOLD, marginTop: 2 }}>{untag(extra.recognition)}</span> : null}
          {extra?.label ? <span data-intent-label style={{ display: 'block', fontSize: 12.5, color: dim, marginTop: 2 }}>{untag(extra.label)}</span> : null}
          {extra?.availability_words ? <span style={{ display: 'block', fontSize: 12.5, color: dim, marginTop: 2 }}>{untag(extra.availability_words)}</span> : null}
          {extra?.how_far_words ? <span style={{ display: 'block', fontSize: 12.5, color: dim, marginTop: 2 }}>{untag(extra.how_far_words)}</span> : null}
          {extra?.reason ? <span data-pick-reason style={{ display: 'block', fontSize: 12.5, color: GOLD, marginTop: 4 }}>{untag(extra.reason)}</span> : null}
        </span>
      </button>
      <div style={{ padding: '8px 12px 12px', display: 'flex', gap: 8 }}>
        <button type="button" data-card-action={action ? 'hand_over' : 'book'} onClick={() => (action ? action.onClick() : onBook(untag(card.name), card.place_id))} style={{ padding: '8px 14px', borderRadius: 999, border: `1px solid ${GOLD}`, background: GOLD, color: '#111', fontWeight: 700 }}>{action ? action.label : 'Book'}</button>
        {noDetails ? null : <button type="button" onClick={() => setOpen(true)} style={{ padding: '8px 14px', borderRadius: 999, border: `1px solid ${GOLD}`, background: 'transparent', color: tone === 'dark' ? GOLD : '#7a5c00', fontWeight: 700 }}>Details</button>}
      </div>
      {open ? <PlaceSheet card={card} sourcesUrl={extra?.sources_url} onClose={() => setOpen(false)} onBook={() => { setOpen(false); onBook(untag(card.name), card.place_id) }} /> : null}
    </div>
  )
}

/** The detail sheet: photos, the venue's own site, hours, prices and what it is — each with its source — and Book. */
export function PlaceSheet({ card, onClose, onBook, sourcesUrl }: { card: Ev; onClose: () => void; onBook: () => void; sourcesUrl?: string | null }) {
  const [place, setPlace] = useState<Ev>(card.place || card)
  const [reading, setReading] = useState(true)
  useEffect(() => {
    let live = true
    fetch(`/api/place/${encodeURIComponent(card.place_id)}`, { cache: 'no-store' }).then(r => r.json()).then(j => {
      if (live && j?.ok && j.place) setPlace(j.place)
    }).catch(() => { /* the card's own facts stay */ }).finally(() => { if (live) setReading(false) })
    return () => { live = false }
  }, [card.place_id])
  useEffect(() => {   // Sasha 252 · Escape closes it, as any dialog (found by EU 251's run: the sheet stayed over the chat)
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
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
          {/* Sasha 293 · the way back, named as the booking hand-off names it (Tyler, 26 Oct: "How do I get back to Sasha?") */}
          <button type="button" data-back-to-sasha onClick={onClose} style={{ padding: '6px 14px', borderRadius: 999, border: `1px solid ${GOLD}`, background: 'transparent', color: GOLD, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' }}>Back to Sasha</button>
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
          {/* Sasha 293 · "Website": their own site (AgAPI's), else their Google listing — a new tab, so her conversation stays where it is */}
          {place.website || place.listing_url ? <a data-website href={place.website || place.listing_url} target="_blank" rel="noopener noreferrer" style={{ padding: '10px 16px', borderRadius: 999, border: `1px solid ${GOLD}`, color: GOLD, fontWeight: 700, textDecoration: 'none' }}>{place.website ? 'Website ↗' : 'Their Google listing ↗'}</a> : null}
          {place.website && place.listing_url ? <a href={place.listing_url} target="_blank" rel="noopener noreferrer" style={{ padding: '10px 16px', borderRadius: 999, border: '1px solid rgba(255,255,255,.25)', color: '#fff', textDecoration: 'none' }}>Google Maps ↗</a> : null}
        </div>
        {sourcesUrl ? <div style={{ marginTop: 12, fontSize: 12 }}><a data-our-sources href={sourcesUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'rgba(255,255,255,.6)' }}>Our sources</a></div> : null}
      </div>
    </div>)
}
