/**
 * Sasha 248 · ONE PLACE CARD's rules (PlaceCard.tsx): a place's facts as shown — each with its source. The site's own words are
 * the fact; Google's category is only "listed on the map as …" (agapi/venue_truth decides that once; this never invents a label).
 */

/** {type, hours, price} — from the place shape (card.place, or the place itself); never from the search's words. */
export function placeFacts(card) {
  const p = (card && card.place) || card || {}
  const t0 = p.type && typeof p.type === 'object' ? p.type
    : (card && card.type ? { value: card.type, source: card.type_source || (/^listed on the map as /.test(card.type) ? 'map' : null) } : null)
  // Sasha 250 · what it is: their own site's words only — a map category (even labelled) from a card kept before is never shown
  const t = t0 && t0.source !== 'map' && !/^listed on the map as /.test(String(t0.value || '')) ? t0 : null
  return { type: t, hours: p.hours && typeof p.hours === 'object' ? p.hours : null, price: p.price && typeof p.price === 'object' ? p.price : null }
}

/** The card's picture and its credit mark: the venue's own (its site) or Google's (credited, as Google's terms ask). */
export function photoOf(card) {
  const c = card || {}
  if (c.photo) return { url: c.photo, mark: /googleusercontent|googleapis|ggpht/.test(c.photo) ? 'Google' : 'their site' }
  if (c.gphoto && c.gphoto.uri) return { url: c.gphoto.uri, mark: 'Google' }
  const p = c.place || {}
  if (Array.isArray(p.photos) && p.photos.length) return { url: p.photos[0], mark: p.photos_source === 'google' ? 'Google' : 'their site' }
  return null
}

/** "From their own site" / "Google" — said under every fact. */
export function sourceWord(f) {
  if (!f) return ''
  return f.source === 'site' ? 'From their own site' : f.source === 'map' ? 'From the map listing' : f.source === 'google' ? 'From Google' : ''
}

/** Sasha 250 · why their site couldn't be read, as one sentence (an older card may carry the engine's {rule, say, …}). */
export function cantRead(p) {
  const x = p && p.cant_read
  return !x ? null : typeof x === 'object' ? String(x.say || x.evidence || x.rule || "their site couldn't be read") : String(x)
}
