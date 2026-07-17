'use client'

import { useState } from 'react'
import { ExternalLink, Hotel, MapPin, Sparkles, Share2, Check, Star, Download } from 'lucide-react'
import TripMap from './TripMap'

const esc = (s: string) => (s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string))

function buildItineraryHtml(it: RichItinerary): string {
  const days = (it.days || []).map(d => `
    <section class="day">
      ${d.image ? `<img src="${d.image}" alt="">` : ''}
      <div class="body">
        <div class="badge">Day ${d.day} · ${esc(d.city)}</div>
        <h2>${esc(d.title)}</h2>
        <p class="desc">${esc(d.description)}</p>
        <ul>${(d.activities || []).map(a => `<li><b>${esc(a.time)}:</b> ${esc(a.name)}${a.blurb ? ` — <span class="muted">${esc(a.blurb)}</span>` : ''}</li>`).join('')}</ul>
        ${d.hotel ? `<p class="hotel">🏨 <b>${esc(d.hotel.name)}</b>${d.hotel.rating ? ` · ${d.hotel.rating}/10` : ''} — <a href="${d.hotel.book_url}">Book on Booking.com</a></p>` : ''}
      </div>
    </section>`).join('')
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(it.title)}</title>
<style>
  *{box-sizing:border-box} body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0e1117;color:#e7e7ea;margin:0;padding:32px;max-width:780px;margin:0 auto}
  h1{color:#DAA520;margin:0 0 4px} .sum{color:#9aa0aa;margin:0 0 6px} .meta{color:#6b7280;font-size:13px;margin-bottom:24px}
  .day{background:#161a22;border:1px solid #232936;border-radius:16px;overflow:hidden;margin-bottom:18px;page-break-inside:avoid}
  .day img{width:100%;height:180px;object-fit:cover;display:block} .body{padding:16px}
  .badge{display:inline-block;background:#DAA520;color:#1a1a1a;font-weight:700;font-size:12px;padding:3px 10px;border-radius:999px;margin-bottom:8px}
  h2{margin:0 0 6px;font-size:18px} .desc{color:#aeb4bf;margin:0 0 10px;line-height:1.5}
  ul{margin:0 0 10px;padding-left:18px} li{margin:4px 0;color:#cdd2da} .muted{color:#7c828d}
  .hotel{background:rgba(218,165,32,.08);border:1px solid rgba(218,165,32,.25);border-radius:10px;padding:8px 12px;margin:6px 0 0;font-size:14px}
  a{color:#DAA520} .total{font-size:20px;font-weight:700;text-align:right;margin-top:20px;padding-top:16px;border-top:1px solid #232936}
  .total span{color:#DAA520}
  @media print{body{background:#fff;color:#111}.day{background:#fafafa;border-color:#ddd}.desc,.muted{color:#444}h1{color:#9a7008}}
</style></head><body>
  <h1>${esc(it.title)}</h1>
  <p class="sum">${esc(it.summary || '')}</p>
  <p class="meta">${(it.days || []).length} days · Discover Vietnam — AI Travel Concierge</p>
  ${days}
  <div class="total">Estimated total: <span>$${(it.estimated_total_usd || 0).toLocaleString()}</span></div>
</body></html>`
}

export interface ItineraryActivity { time: string; name: string; blurb: string; book_url: string }
export interface ItineraryDay {
  day: number
  city: string
  title: string
  description: string
  image?: string | null
  hotel?: { name: string; book_url: string; rating?: number; reviews?: number; tag?: string } | null
  activities: ItineraryActivity[]
}
export interface RichItinerary {
  title: string
  summary: string
  days: ItineraryDay[]
  estimated_total_usd: number
}

const GOLD = '#DAA520'

function copyText(itinerary: RichItinerary): string {
  const lines = [itinerary.title, itinerary.summary, '']
  for (const d of itinerary.days || []) {
    lines.push(`Day ${d.day} — ${d.city}: ${d.title}`)
    for (const a of d.activities || []) lines.push(`  • ${a.time}: ${a.name}`)
    if (d.hotel) lines.push(`  Stay: ${d.hotel.name}`)
    lines.push('')
  }
  lines.push(`Estimated total: $${(itinerary.estimated_total_usd || 0).toLocaleString()}`)
  return lines.join('\n')
}

export default function ItineraryDays({ itinerary, onBook, onRevise }: { itinerary: RichItinerary; onBook?: () => void; onRevise?: (text: string) => void }) {
  const [copied, setCopied] = useState(false)
  const share = async () => {
    try { await navigator.clipboard.writeText(copyText(itinerary)); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch {}
  }
  const download = () => {
    const blob = new Blob([buildItineraryHtml(itinerary)], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(itinerary.title || 'Vietnam-Itinerary').replace(/[^a-z0-9]+/gi, '-')}.html`
    document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-base font-semibold truncate" style={{ color: GOLD }}>{itinerary.title}</div>
            {itinerary.summary && <div className="text-xs text-white/40 mt-0.5">{itinerary.summary}</div>}
          </div>
          <div className="flex-shrink-0 flex items-center gap-1.5">
            <button onClick={download} title="Download itinerary"
              className="inline-flex items-center gap-1 text-xs rounded-lg px-2.5 py-1.5 border transition-colors hover:bg-white/5"
              style={{ borderColor: 'rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.6)' }}>
              <Download className="w-3 h-3" />Download
            </button>
            <button onClick={share} title="Copy / share itinerary"
              className="inline-flex items-center gap-1 text-xs rounded-lg px-2.5 py-1.5 border transition-colors hover:bg-white/5"
              style={{ borderColor: 'rgba(255,255,255,0.12)', color: copied ? '#34d399' : 'rgba(255,255,255,0.6)' }}>
              {copied ? <Check className="w-3 h-3" /> : <Share2 className="w-3 h-3" />}{copied ? 'Copied' : 'Share'}
            </button>
          </div>
        </div>
        <div className="text-xs text-white/30 mt-1">{itinerary.days?.length || 0} days · Tap any “Book” to reserve</div>
      </div>

      {/* Days */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        <TripMap days={itinerary.days} />

        {onRevise && (
          <div className="flex gap-1.5 flex-wrap">
            {[
              { label: '💰 More budget-friendly', msg: 'Rebuild my itinerary on a more budget-friendly basis with cheaper hotels.' },
              { label: '✨ More luxurious', msg: 'Rebuild my itinerary to be more luxurious with 5-star hotels.' },
              { label: '➕ Add a day', msg: 'Add an extra day to my itinerary.' },
            ].map(b => (
              <button key={b.label} onClick={() => onRevise(b.msg)}
                className="text-xs rounded-full px-3 py-1 transition-opacity hover:opacity-80"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.6)' }}>
                {b.label}
              </button>
            ))}
          </div>
        )}
        {itinerary.days?.map((d) => (
          <div key={d.day} className="rounded-2xl overflow-hidden border border-white/5 transition-colors hover:border-white/15" style={{ background: 'rgba(255,255,255,0.02)' }}>
            {d.image && (
              <div className="relative h-32 w-full">
                <img src={d.image} alt={d.title} className="w-full h-full object-cover" />
                <div className="absolute inset-0" style={{ background: 'linear-gradient(to top, rgba(10,10,16,0.9), transparent 60%)' }} />
                <div className="absolute top-2 left-2 text-xs font-bold px-2.5 py-1 rounded-full" style={{ background: GOLD, color: '#1a1a1a' }}>
                  Day {d.day}
                </div>
                <div className="absolute bottom-2 left-3 right-3">
                  <div className="text-sm font-semibold text-white leading-tight">{d.title}</div>
                  <div className="text-[11px] text-white/70 flex items-center gap-1"><MapPin className="w-3 h-3" />{d.city}</div>
                </div>
              </div>
            )}
            <div className="p-3 space-y-2.5">
              {!d.image && (
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full" style={{ background: GOLD, color: '#1a1a1a' }}>Day {d.day}</span>
                  <span className="text-sm font-semibold text-white/85">{d.title}</span>
                  <span className="text-[11px] text-white/40">· {d.city}</span>
                </div>
              )}
              {d.description && <div className="text-xs text-white/55 leading-relaxed">{d.description}</div>}

              {/* Activities */}
              {d.activities?.length > 0 && (
                <div className="space-y-1.5">
                  {d.activities.map((a, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <Sparkles className="w-3 h-3 mt-0.5 flex-shrink-0" style={{ color: GOLD }} />
                      <div className="flex-1 min-w-0">
                        <a href={a.book_url} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-white/80 hover:text-white inline-flex items-center gap-1 group">
                          <span className="text-white/35">{a.time}:</span> {a.name}
                          <ExternalLink className="w-2.5 h-2.5 opacity-0 group-hover:opacity-60" />
                        </a>
                        {a.blurb && <div className="text-[11px] text-white/35">{a.blurb}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Hotel for the night */}
              {d.hotel && (
                <div className="flex items-center gap-2 rounded-xl px-3 py-2 mt-1" style={{ background: 'rgba(218,165,32,0.08)', border: '1px solid rgba(218,165,32,0.2)' }}>
                  <Hotel className="w-3.5 h-3.5 flex-shrink-0" style={{ color: GOLD }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] uppercase tracking-wider text-white/30">Stay</div>
                    <div className="text-xs text-white/80 truncate">{d.hotel.name}</div>
                    {d.hotel.rating && (
                      <div className="text-[10px] text-white/45 flex items-center gap-1">
                        <Star className="w-2.5 h-2.5" style={{ color: GOLD, fill: GOLD }} />
                        {d.hotel.rating}/10 · {d.hotel.tag}
                      </div>
                    )}
                  </div>
                  <a href={d.hotel.book_url} target="_blank" rel="noopener noreferrer"
                    className="text-xs font-medium rounded-lg px-3 py-1.5 flex-shrink-0 transition-opacity hover:opacity-85"
                    style={{ background: `linear-gradient(135deg, ${GOLD}, #B8860B)`, color: '#fff' }}>
                    Book
                  </a>
                </div>
              )}
            </div>
          </div>
        ))}

        <div className="text-center text-[11px] text-white/30 pt-1 pb-2">
          💬 Tell Sasha to swap a hotel, add a day, or change the pace — she’ll rebuild it.
        </div>
      </div>

      {/* Footer total + book all */}
      <div className="px-4 py-3 border-t border-white/5 flex-shrink-0" style={{ background: 'rgba(0,0,0,0.3)' }}>
        <div className="flex justify-between items-center mb-2">
          <span className="text-xs text-white/40">Estimated total</span>
          <span className="text-lg font-semibold text-white">${(itinerary.estimated_total_usd || 0).toLocaleString()}</span>
        </div>
        <button onClick={onBook}
          className="w-full py-2.5 rounded-xl text-sm font-medium transition-opacity hover:opacity-90"
          style={{ background: `linear-gradient(135deg, ${GOLD}, #B8860B)`, color: '#fff' }}>
          Book this trip
        </button>
      </div>
    </div>
  )
}
