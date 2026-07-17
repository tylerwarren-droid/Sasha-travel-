// Builds a self-contained, printable HTML document for a booked itinerary (used for
// "Download PDF" via the browser print dialog) plus a plain-text summary (used for the
// Share button / clipboard fallback). No external dependencies.

function esc(s: any): string {
  return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string))
}

export function buildItineraryHtml(it: any, ref?: string): string {
  // A booking reference means this trip is PAID FOR. The stays are reserved, so offering to
  // "Book" each hotel underneath a "Booking confirmed" banner is both contradictory and
  // dangerous — a guest following those links would pay for the same rooms twice. Once a ref
  // exists, every booking call-to-action becomes a statement of what's already reserved.
  const isBooked = Boolean(ref)
  const days = (it?.days || []).map((d: any) => {
    const hotel = d.hotel && d.hotel.name ? d.hotel : null
    const acts = (d.activities || []).map((a: any) =>
      `<li><b>${esc(a.time)}:</b> ${esc(a.name)}${a.blurb ? ` — <span class="muted">${esc(a.blurb)}</span>` : ''}</li>`
    ).join('')
    const hotelCta = isBooked
      ? ' — <span class="reserved">Reserved</span>'
      : (hotel?.book_url ? ` — <a href="${esc(hotel.book_url)}">Book</a>` : '')
    return `<section class="day">
      <div class="badge">Day ${esc(d.day)} · ${esc(d.city)}</div>
      <h2>${esc(d.title)}</h2>
      ${d.description ? `<p class="desc">${esc(d.description)}</p>` : ''}
      ${acts ? `<ul>${acts}</ul>` : ''}
      ${hotel ? `<p class="hotel">🏨 <b>${esc(hotel.name)}</b>${hotel.rating ? ` · ${esc(hotel.rating)}/10` : ''}${hotel.price_from ? ` · $${esc(hotel.price_from)}/night` : ''}${hotelCta}</p>` : ''}
    </section>`
  }).join('')
  const cb = it?.cost_breakdown
  const breakdown = cb
    ? `<p class="meta">Hotels $${Number(cb.hotels || 0).toLocaleString()} · Experiences $${Number(cb.experiences || 0).toLocaleString()} · Meals $${Number(cb.meals || 0).toLocaleString()} · Transfers $${Number(cb.transport || 0).toLocaleString()}</p>`
    : ''
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(it?.title || 'Vietnam Itinerary')}</title>
<style>
*{box-sizing:border-box} body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#fff;color:#1a1a1a;margin:0;padding:36px;max-width:780px;margin:0 auto}
.brand{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#B8860B;font-weight:700}
h1{color:#9a7008;margin:6px 0 2px;font-size:26px} .sum{color:#555;margin:0 0 4px} .meta{color:#777;font-size:13px;margin:2px 0 0}
.ref{display:inline-block;margin:14px 0 24px;background:#faf3e0;border:1px solid #e8d9a8;color:#8a6d10;border-radius:8px;padding:7px 12px;font-size:13px;font-weight:600}
.day{border:1px solid #eee;border-radius:14px;padding:16px 18px;margin-bottom:14px;page-break-inside:avoid}
.badge{display:inline-block;background:#DAA520;color:#1a1a1a;font-weight:700;font-size:12px;padding:3px 10px;border-radius:999px;margin-bottom:8px}
h2{margin:0 0 6px;font-size:18px} .desc{color:#444;margin:0 0 10px;line-height:1.5}
ul{margin:0 0 10px;padding-left:18px} li{margin:4px 0;color:#333} .muted{color:#888}
.hotel{background:#faf6ea;border:1px solid #ecdcae;border-radius:10px;padding:8px 12px;margin:8px 0 0;font-size:14px}
.reserved{color:#2f7d54;font-weight:700}
a{color:#B8860B} .total{font-size:22px;font-weight:800;text-align:right;margin-top:18px;padding-top:14px;border-top:2px solid #eee}
.total span{color:#9a7008}
.foot{margin-top:24px;color:#999;font-size:12px;text-align:center}
@media print{body{padding:0}.day{border-color:#ddd}}
</style></head><body>
  <div class="brand">🇻🇳 Discover Vietnam · AI Travel Concierge</div>
  <h1>${esc(it?.title || 'Your Vietnam Itinerary')}</h1>
  ${it?.summary ? `<p class="sum">${esc(it.summary)}</p>` : ''}
  ${ref ? `<div class="ref">✓ Booking confirmed · Ref ${esc(ref)}</div>` : ''}
  ${days}
  <div class="total">${isBooked ? 'Total paid' : 'Estimated total'}: <span>$${Number(it?.estimated_total_usd || 0).toLocaleString()}</span></div>
  ${breakdown}
  <div class="foot">${isBooked
    ? 'Booked with Sasha · Discover Vietnam. Keep this reference for your records.'
    : 'Planned with Sasha · Discover Vietnam. This trip is not booked yet.'}</div>
</body></html>`
}

export function buildItineraryText(it: any, ref?: string): string {
  const lines: string[] = [`${it?.title || 'Vietnam Itinerary'}`]
  if (it?.summary) lines.push(it.summary)
  if (ref) lines.push(`Booking ref: ${ref}`)
  lines.push('')
  for (const d of it?.days || []) {
    lines.push(`Day ${d.day} — ${d.city}: ${d.title}`)
    for (const a of d.activities || []) lines.push(`  • ${a.time}: ${a.name}`)
    if (d.hotel?.name) lines.push(`  Stay: ${d.hotel.name}`)
    lines.push('')
  }
  lines.push(`${ref ? 'Total paid' : 'Estimated total'}: $${Number(it?.estimated_total_usd || 0).toLocaleString()}`)
  return lines.join('\n')
}
