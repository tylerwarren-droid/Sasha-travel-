'use client'
import { useState, useEffect } from 'react'

interface Photo {
  url: string
  thumb: string
  description: string
  photographer: string
  unsplash_url: string
}

interface FotoStripProps {
  query: string
  type?: string
  visible: boolean
}

export default function FotoStrip({ query, type = 'general', visible }: FotoStripProps) {
  const [photos, setPhotos] = useState<Photo[]>([])
  const [loading, setLoading] = useState(false)
  const [activePhoto, setActivePhoto] = useState(0)

  useEffect(() => {
    if (!visible || !query) return
    const fetchPhotos = async () => {
      setLoading(true)
      try {
        const res = await fetch('https://sasha-travel-production.up.railway.app/api/photos/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, type, count: 3 })
        })
        const data = await res.json()
        setPhotos(data.photos || [])
        setActivePhoto(0)
      } catch (e) {
        console.error('Foto fetch error:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchPhotos()
  }, [query, type, visible])

  if (!visible) return null

  return (
    <div className="w-full rounded-2xl overflow-hidden border border-white/5 bg-black/30" style={{ height: '200px' }}>
      {loading && (
        <div className="w-full h-full flex items-center justify-center">
          <div className="text-white/30 text-xs animate-pulse">Finding photos...</div>
        </div>
      )}
      {!loading && photos.length > 0 && (
        <div className="relative w-full h-full">
          {/* Main photo */}
          <img
            src={photos[activePhoto]?.url}
            alt={photos[activePhoto]?.description}
            className="w-full h-full object-cover transition-opacity duration-500"
          />
          {/* Overlay */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
          {/* Caption */}
          <div className="absolute bottom-2 left-3 right-3">
            <div className="text-white/70 text-xs truncate">{photos[activePhoto]?.description}</div>
            <div className="text-white/30 text-xs">📷 {photos[activePhoto]?.photographer}</div>
          </div>
          {/* Thumbnail strip */}
          {photos.length > 1 && (
            <div className="absolute top-2 right-2 flex gap-1">
              {photos.map((p, i) => (
                <button
                  key={i}
                  onClick={() => setActivePhoto(i)}
                  className={`w-10 h-7 rounded overflow-hidden border-2 transition-all ${i === activePhoto ? 'border-white' : 'border-white/20'}`}
                >
                  <img src={p.thumb} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {!loading && photos.length === 0 && (
        <div className="w-full h-full flex items-center justify-center">
          <div className="text-white/20 text-xs">No photos found</div>
        </div>
      )}
    </div>
  )
}
