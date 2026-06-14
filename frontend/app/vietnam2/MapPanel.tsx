'use client'

import { useEffect, useRef } from 'react'

interface Location {
  name: string
  lat: number
  lng: number
  type: string
  description: string
}

interface MapPanelProps {
  locations: Location[]
}

const typeConfig: Record<string, { color: string; emoji: string }> = {
  culture: { color: '#DAA520', emoji: '🏛' },
  nature: { color: '#10B981', emoji: '🌿' },
  city: { color: '#3B82F6', emoji: '🏙' },
  beach: { color: '#06B6D4', emoji: '🏖' },
  hotel: { color: '#8B5CF6', emoji: '🏨' },
  restaurant: { color: '#F59E0B', emoji: '🍽' },
  golf: { color: '#84CC16', emoji: '⛳' },
  default: { color: '#DAA520', emoji: '📍' },
}

export default function MapPanel({ locations }: MapPanelProps) {
  const mapRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (typeof window === 'undefined' || !containerRef.current) return
    import('leaflet').then(L => {
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null }
      delete (L.Icon.Default.prototype as any)._getIconUrl
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
        iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
      })
      const map = L.map(containerRef.current!, { center: [16.0, 107.5], zoom: 6, zoomControl: true, attributionControl: false })
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { subdomains: 'abcd', maxZoom: 19 }).addTo(map)
      locations.forEach(loc => {
        const cfg = typeConfig[loc.type] || typeConfig.default
        const icon = L.divIcon({
          className: '',
          html: `<div style="width:36px;height:36px;background:${cfg.color};border:2px solid rgba(255,255,255,0.3);border-radius:50% 50% 50% 0;transform:rotate(-45deg);box-shadow:0 4px 12px rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;"><span style="transform:rotate(45deg);font-size:14px;">${cfg.emoji}</span></div>`,
          iconSize: [36, 36], iconAnchor: [18, 36], popupAnchor: [0, -36],
        })
        L.marker([loc.lat, loc.lng], { icon }).addTo(map).bindPopup(`
          <div style="background:#0d0d1e;border:1px solid rgba(218,165,32,0.3);border-radius:12px;padding:12px;min-width:180px;font-family:system-ui,sans-serif;">
            <div style="font-size:11px;color:${cfg.color};font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">${cfg.emoji} ${loc.type}</div>
            <div style="font-size:14px;font-weight:700;color:#F5F0E8;margin-bottom:4px;">${loc.name}</div>
            <div style="font-size:12px;color:rgba(255,255,255,0.4);">${loc.description}</div>
          </div>`, { closeButton: false, className: 'sasha-popup' })
      })
      mapRef.current = map
    })
    return () => { if (mapRef.current) { mapRef.current.remove(); mapRef.current = null } }
  }, [locations])

  return (
    <div className="relative w-full h-full" style={{ background: '#06060F' }}>
      <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
      <div ref={containerRef} className="w-full h-full" />
      <div className="absolute bottom-4 left-4 rounded-xl p-3 z-[1000]" style={{ background: 'rgba(6,6,15,0.9)', border: '1px solid rgba(218,165,32,0.2)', backdropFilter: 'blur(10px)' }}>
        <div className="text-xs font-semibold mb-2" style={{ color: 'rgba(218,165,32,0.8)' }}>LEGEND</div>
        {Object.entries(typeConfig).filter(([k]) => k !== 'default').map(([type, cfg]) => (
          <div key={type} className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: cfg.color }} />
            <span className="text-xs capitalize" style={{ color: 'rgba(255,255,255,0.5)' }}>{type}</span>
          </div>
        ))}
      </div>
      <style>{`
        .sasha-popup .leaflet-popup-content-wrapper { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
        .sasha-popup .leaflet-popup-tip-container { display: none; }
        .sasha-popup .leaflet-popup-content { margin: 0 !important; }
        .leaflet-control-zoom { border: 1px solid rgba(218,165,32,0.2) !important; }
        .leaflet-control-zoom a { background: rgba(6,6,15,0.9) !important; color: #DAA520 !important; border-color: rgba(218,165,32,0.2) !important; }
      `}</style>
    </div>
  )
}
