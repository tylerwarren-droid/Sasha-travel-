// Sasha 246 · the Subscriptions card's heading says what was FOUND: none → "No subscriptions found" (it showed a heading and a
// "tap one to cancel it" line built for a list, over an empty one); some → the monthly total, as before.

/** The card's heading: none found → "No subscriptions found"; a list with a total → "About <total> a month"; else none. */
export function subsHeading(items, total) {
  const n = Array.isArray(items) ? items.length : 0
  if (n === 0) return 'No subscriptions found'
  return total ? `About ${total} a month` : undefined
}

/** The card's small print: where it was read from, and — only when there is something to tap — how to cancel one. */
export function subsFooter(items, source) {
  const n = Array.isArray(items) ? items.length : 0
  const from = `From ${source || 'your receipts'}`
  return n === 0 ? `${from} · nothing to cancel` : `${from} · tap one to cancel it — nothing happens until you say yes`
}
