'use client'

import { ItineraryDay } from './ItineraryDays'

// Approximate geographic positions (0-100) for Vietnam destinations, north → south. Used
// only to preserve relative order/orientation; the route is then auto-fit to fill the panel.
const COORDS: Record<string, { x: number; y: number }> = {
  'Sapa': { x: 34, y: 9 },
  'Hanoi': { x: 45, y: 15 },
  'Ha Long Bay': { x: 57, y: 17 },
  'Ninh Binh': { x: 46, y: 22 },
  'Hue': { x: 58, y: 41 },
  'Da Nang': { x: 62, y: 47 },
  'Hoi An': { x: 63, y: 49 },
  'Da Lat': { x: 59, y: 70 },
  'Nha Trang': { x: 69, y: 66 },
  'Mui Ne': { x: 63, y: 77 },
  'Ho Chi Minh City': { x: 53, y: 84 },
  'Mekong Delta': { x: 45, y: 90 },
  'Phu Quoc': { x: 31, y: 86 },
  'Con Dao': { x: 56, y: 94 },
}

const PAD = 16  // % padding around the fitted route

export default function TripMap({ days }: { days: ItineraryDay[] }) {
  const raw: { city: string; x: number; y: number; day: number }[] = []
  for (const d of days || []) {
    const c = COORDS[d.city]
    if (c && raw[raw.length - 1]?.city !== d.city) raw.push({ city: d.city, ...c, day: d.day })
  }
  if (raw.length < 2) return null

  // Auto-fit: scale the true coords to fill the panel (no more pins stuck in a corner).
  const xs = raw.map(s => s.x), ys = raw.map(s => s.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
  const fit = (v: number, lo: number, hi: number) => (hi === lo ? 50 : PAD + ((v - lo) / (hi - lo)) * (100 - 2 * PAD))
  const stops = raw.map(s => ({ ...s, fx: fit(s.x, minX, maxX), fy: fit(s.y, minY, maxY) }))
  const line = stops.map(s => `${s.fx},${s.fy}`).join(' ')

  return (
    <div className="relative rounded-2xl overflow-hidden border border-white/5" style={{ height: 150, background: 'radial-gradient(120% 90% at 30% 0%, #13283b, #0a0f16 70%)' }}>
      {/* faint dotted texture */}
      <div className="absolute inset-0 opacity-[0.12]" style={{ backgroundImage: 'radial-gradient(rgba(218,165,32,0.6) 0.5px, transparent 0.5px)', backgroundSize: '14px 14px' }} />
      <div className="absolute top-2.5 left-3 text-[10px] uppercase tracking-[0.22em] text-white/40 z-10 flex items-center gap-1.5">
        <span style={{ color: '#DAA520' }}>◆</span> Your route · {stops.length} stops
      </div>

      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 w-full h-full">
        <defs>
          <linearGradient id="routeline" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#DAA520" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#DAA520" stopOpacity="0.45" />
          </linearGradient>
        </defs>
        <polyline points={line} fill="none" stroke="url(#routeline)" strokeWidth="0.7" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="2 1.6" />
      </svg>

      {stops.map((s, i) => (
        <div key={i} className="absolute -translate-x-1/2 -translate-y-1/2 flex items-center gap-1.5" style={{ left: `${s.fx}%`, top: `${s.fy}%` }}>
          <span className="rounded-full flex items-center justify-center text-[9px] font-bold ring-2 ring-black/40" style={{ width: 18, height: 18, background: '#DAA520', color: '#1a1a1a', boxShadow: '0 0 10px rgba(218,165,32,0.7)' }}>{s.day}</span>
          <span className="text-[11px] font-medium text-white/85 whitespace-nowrap px-1.5 py-0.5 rounded-md" style={{ background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(2px)' }}>{s.city}</span>
        </div>
      ))}
    </div>
  )
}
