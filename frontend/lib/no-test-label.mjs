// Sasha 218 · the founder's call: NO visible "TEST" label on /next's cards or its right-hand panel (desktop and phone). Test mode
// itself is untouched underneath — the backend still runs, prices and marks everything as TEST; only what the page SHOWS loses
// the tag. (Stripe's own test page keeps Stripe's banner.) Display-only: never applied to ids, links or anything sent back.

const PATTERNS = [
  [/\s*\((?:Duffel\s+)?TEST\b[^)]*\)/g, ''],      // "(TEST)", "(TEST — nothing is charged)", "(Duffel TEST)"
  [/\s*·\s*TEST\b(?!\s*[—-])/g, ''],              // "… · TEST"
  [/\bTEST\s*·\s*/g, ''],                          // "TEST · booked"
  [/\bTEST\s*[—-]\s*/g, ''],                       // "TEST — …"
  [/\bDuffel TEST\b/g, 'Duffel'],
  [/,?\s*marked TEST,?/g, ','],
  [/\bTEST\s+(?=[a-z€$£\d])/g, ''],                // "TEST payment", "TEST fare", "TEST €…"
  [/\s+\bTEST\b(?=[.,;:!]|$)/g, ''],               // a trailing "… TEST"
  [/\s*\(test\)/g, ''],                            // a fixture place "Casa Marea (test)"
  // Sasha 404 · the stand-in is a DEMO supplier: its mark (booking_signer/supplier.py) is never stripped here (Sasha 219's pattern is gone)
]
const SKIP_KEYS = new Set(['url', 'href', 'links', 'id', 'place_id', 'offer_id', 'trip_id', 'session_id', 'checkout_url', 'view_url',
                           'page_url', 'turn', 'kind', 'type', 'what', 'status', 'focus', 'highlight'])

/** Sasha 404 · a DEMO supplier's mark (booking_signer/supplier.py SUFFIX / STANDIN): this file can never remove it — each one is held
 *  aside before the patterns run and put back after (KANOE "THE DMC SPACE": a demo supplier always shows it is a demo). */
export const DEMO_MARKS = [' · Demo stand-in', ' · Demo']

/** One string, its TEST labels removed (and the spacing they leave tidied). A demo supplier's mark is never touched. */
export function untag(s) {
  if (typeof s !== 'string' || !/test/i.test(s)) return s   // (every pattern above contains "test")
  const held = []
  let t = s
  for (const m of DEMO_MARKS) t = t.split(m).join(`\u0000${held.push(m) - 1}\u0000`)
  for (const [rx, to] of PATTERNS) t = t.replace(rx, to)
  t = t.replace(/\s{2,}/g, ' ').replace(/\s+([.,;:!)])/g, '$1').replace(/,\s*,/g, ',').trim()
  return t.replace(/\u0000(\d+)\u0000/g, (_, i) => held[Number(i)])
}

/** A whole render event / panel payload, every display string untagged; ids, links and kinds left exactly as they are. */
export function untagDeep(v, key = '') {
  if (SKIP_KEYS.has(key)) return v
  if (typeof v === 'string') return untag(v)
  if (Array.isArray(v)) return v.map(x => untagDeep(x))
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, untagDeep(x, k)]))
  return v
}
