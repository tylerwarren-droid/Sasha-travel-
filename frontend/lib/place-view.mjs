/**
 * Sasha 248 · ONE PLACE CARD's rules (PlaceCard.tsx): a place's facts as shown — each with its source. The site's own words are
 * the fact; Google's category is only "listed on Google as …" (agapi/venue_truth decides that once; this never invents a label).
 */

/** {type, hours, price} — from the place shape (card.place, or the place itself); never from the search's words. */
export function placeFacts(card) {
  const p = (card && card.place) || card || {}
  const t = p.type && typeof p.type === 'object' ? p.type
    : (card && card.type ? { value: card.type, source: card.type_source || (/^listed on Google as /.test(card.type) ? 'google' : null) } : null)
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
  return f.source === 'site' ? 'From their own site' : f.source === 'google' ? 'From Google' : ''
}
