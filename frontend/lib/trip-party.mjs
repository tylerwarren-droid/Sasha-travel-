// Sasha 246 · the Trip tab's TRAVELLERS is the trip's own party — the plan's `party` (how many they said, kept on the plan and
// its basket rows), never the page's default (/s2 passed 1, and a trip for two showed "Travellers 1"). The page's number is the
// last resort, used only when the plan says nothing.
// Sasha 249 · ONE PARTY: the trip's figures (the server's trip_figures.party — the plan's, else its basket rows') come first, and
// nothing known is null — the tab shows "—" and Sasha asks; never a silent 1 or 2.

const n = (v) => {
  const x = Number(v)
  return Number.isFinite(x) && x >= 1 ? Math.floor(x) : null
}

/** How many are travelling: the trip's figures' party, else the plan's party, else its travellers / travelers, else the
 *  estimate's, else the page's fallback — else null (unknown: shown as "—", never guessed). */
export function partySize(plan, costBreakdown, fallback, figures) {
  const p = plan || {}
  return n((figures || {}).party) ?? n(p.party) ?? n(p.travellers) ?? n(p.travelers) ?? n((costBreakdown || {}).travellers) ?? n(fallback) ?? null
}
