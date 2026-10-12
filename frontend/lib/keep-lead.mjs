// Sasha 246 · MY KEEP's header line names the person's OWN item — the mask Sasha actually sees for one of theirs ("Passport PT
// ••••789") — never a fixed example ("Passport ES ••••456" was shown to everyone, whatever they kept). Nothing kept (or the list
// not read yet) → a neutral line with no example at all.

const TAIL = 'They’re filled in where needed, at that moment, after your yes.'
const PREFER = ['passport', 'national_id', 'trusted_traveller', 'loyalty']   // agapi/keep.py's types

/** The item the header names: a passport first (what most bookings need), then an ID, then any other; null when none. */
export function leadItem(items) {
  const list = (Array.isArray(items) ? items : []).filter((it) => it && typeof it.masked === 'string' && it.masked.trim())
  if (list.length === 0) return null
  for (const t of PREFER) {
    const hit = list.find((it) => it.type === t)
    if (hit) return hit
  }
  return list[0]
}

/** The header line under "My Keep" / "Your Keep". */
export function keepLead(items) {
  const it = leadItem(items)
  return it
    ? `Sasha never sees these — only “${it.masked.trim()}”. ${TAIL}`
    : `Sasha never sees what you keep here — only a masked version of it. ${TAIL}`
}
