'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import SashaAvatar from '../components/SashaAvatar'
import SashaChat from '../components/SashaChat'
import ItineraryPanel from '../components/ItineraryPanel'
import { User, Itinerary } from '@/types'

const DEMO_USER: User = {
  display_name: 'Alex',
  email: 'alex@example.com',
  default_currency: 'USD',
  sasha_context: 'Alex loves cultural immersion, authentic food experiences, and luxury travel across Asia.',
  travellers: [
    { relation: 'self', first_name: 'Alex' },
    { relation: 'partner', first_name: 'Maya' },
  ],
  preferences: [
    { key: 'accommodation.type', value: 'boutique_heritage', source: 'explicit', confidence: 1.0, is_active: true },
    { key: 'experience.type', value: 'culture_and_food', source: 'explicit', confidence: 1.0, is_active: true },
  ],
  past_trips: [
    { title: 'Vietnam — Hanoi and Ha Long Bay', return_date: 'Summer 2024' },
    { title: 'Vietnam — Hoi An and Da Nang', return_date: 'Spring 2023' },
  ],
  ota_affinity: ['culture', 'adventure']
}

const INITIAL_ITINERARY: Itinerary = {
  title: 'Vietnam Discovery',
  ota_channel: 'culture',
  status: 'draft',
  total_fiat: 0,
  items: []
}

interface Photo {
  url: string
  thumb: string
  description: string
  photographer: string
}

export default function VietnamPage() {
  const [itinerary, setItinerary] = useState<Itinerary>(INITIAL_ITINERARY)
  const [speakFn, setSpeakFn] = useState<((text: string) => void) | null>(null)
  const [isListening, setIsListening] = useState(false)
  const [paymentModal, setPaymentModal] = useState<'card' | 'crypto' | null>(null)
  const [photos, setPhotos] = useState<Photo[]>([])
  const [activePhoto, setActivePhoto] = useState(0)
  const [photoQuery, setPhotoQuery] = useState('Vietnam landscape travel')
  const [engaged, setEngaged] = useState(false)
  const photoInterval = useRef<any>(null)

  useEffect(() => {
    const fetchPhotos = async () => {
      try {
        const res = await fetch('https://sasha-travel-production.up.railway.app/api/photos/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: photoQuery, count: 4 })
        })
        const data = await res.json()
        if (data.photos?.length > 0) {
          setPhotos(data.photos)
          setActivePhoto(0)
        }
      } catch (e) {}
    }
    fetchPhotos()
  }, [photoQuery])

  useEffect(() => {
    if (photos.length <= 1) return
    clearInterval(photoInterval.current)
    photoInterval.current = setInterval(() => {
      setActivePhoto(prev => (prev + 1) % photos.length)
    }, 5000)
    return () => clearInterval(photoInterval.current)
  }, [photos])

  const handleAvatarReady = useCallback((speak: (text: string) => void) => {
    setSpeakFn(() => speak)
  }, [])

  const handleSashaResponse = useCallback((text: string) => {
    if (speakFn) speakFn(text)
    setEngaged(true)
    const lower = text.toLowerCase()
    const golfCourses = ['montgomerie', 'hoiana', 'bluffs', 'ba na hills', 'vinpearl golf', 'laguna golf', 'legend danang']
    const destinations = ['danang', 'da nang', 'hanoi', 'hoi an', 'ho chi minh', 'saigon', 'ha long', 'phu quoc', 'nha trang', 'da lat', 'hue', 'sapa', 'ha giang']
    for (const course of golfCourses) {
      if (lower.includes(course)) { setPhotoQuery(`${course} golf Vietnam`); return }
    }
    for (const dest of destinations) {
      if (lower.includes(dest)) { setPhotoQuery(`${dest} Vietnam travel`); return }
    }
  }, [speakFn])

  return (
    <main className="h-screen flex flex-col overflow-hidden" style={{ background: '#080810' }}>

      {/* HEADER */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-white/5 flex-shrink-0" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(10px)' }}>
        <div className="flex items-center gap-3">
          <span className="text-xl">🇻🇳</span>
          <span className="font-bold tracking-wide" style={{ color: '#DAA520' }}>Discover Vietnam</span>
          <div className="w-px h-4 bg-white/10" />
          <span className="text-xs text-white/30 tracking-widest uppercase">AI Travel Concierge</span>
        </div>
        <div className="text-xs px-3 py-1 rounded-full border" style={{ color: '#DAA520', borderColor: 'rgba(218,165,32,0.3)', background: 'rgba(218,165,32,0.1)' }}>
          Ministry of Tourism Partner
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div className="flex-1 flex overflow-hidden p-3 gap-3" style={{ minHeight: 0 }}>

        {/* LEFT COLUMN */}
        <div className="flex flex-col gap-3 overflow-hidden" style={{ width: '55%' }}>

          {/* AVATAR — always present, resizes based on state */}
          <div
            className="rounded-3xl overflow-hidden border border-white/5 flex-shrink-0 transition-all duration-700"
            style={{ height: engaged ? '160px' : '55%' }}
          >
            <SashaAvatar onAvatarReady={handleAvatarReady} isListening={isListening} />
          </div>

          {/* PHOTOS — hidden before engaged, hero after */}
          {engaged && (
            <div className="relative rounded-3xl overflow-hidden border border-white/5 flex-1" style={{ minHeight: 0 }}>
              {photos.length > 0 ? (
                <>
                  <img
                    key={activePhoto}
                    src={photos[activePhoto]?.url}
                    alt={photos[activePhoto]?.description}
                    className="w-full h-full object-cover"
                    style={{ animation: 'fadeIn 0.8s ease' }}
                  />
                  <div className="absolute inset-0" style={{ background: 'linear-gradient(to bottom, transparent 60%, rgba(0,0,0,0.7) 100%)' }} />
                  <div className="absolute bottom-3 left-4 right-16">
                    <div className="text-white/60 text-xs">📷 {photos[activePhoto]?.photographer}</div>
                  </div>
                  <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5">
                    {photos.map((_, i) => (
                      <button key={i} onClick={() => setActivePhoto(i)}
                        className="rounded-full transition-all"
                        style={{ width: i === activePhoto ? '18px' : '6px', height: '6px', background: i === activePhoto ? '#DAA520' : 'rgba(255,255,255,0.3)' }}
                      />
                    ))}
                  </div>
                  <div className="absolute top-3 right-3 flex gap-1.5">
                    {photos.map((p, i) => (
                      <button key={i} onClick={() => setActivePhoto(i)}
                        className="rounded-lg overflow-hidden border-2 transition-all"
                        style={{ width: '44px', height: '32px', borderColor: i === activePhoto ? '#DAA520' : 'rgba(255,255,255,0.2)' }}
                      >
                        <img src={p.thumb} alt="" className="w-full h-full object-cover" />
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <div className="w-full h-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #0a0a1a, #1a1a3a)' }}>
                  <div className="text-white/20 text-sm">Loading photos...</div>
                </div>
              )}
            </div>
          )}

          {/* PHOTO TEASER — only in welcome state */}
          {!engaged && photos.length > 0 && (
            <div className="relative rounded-2xl overflow-hidden border border-white/5 flex-shrink-0" style={{ height: '100px' }}>
              <img src={photos[0]?.url} alt="" className="w-full h-full object-cover opacity-50" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-white/40 text-xs tracking-widest uppercase">Start talking to explore Vietnam</div>
              </div>
            </div>
          )}

          {/* CHAT — always visible, below avatar */}
          <div className="rounded-2xl border border-white/5 overflow-hidden flex-shrink-0" 
            style={{ height: engaged ? '160px' : '35%', background: 'rgba(255,255,255,0.02)', transition: 'height 0.7s ease' }}>
            <SashaChat
              user={DEMO_USER}
              itinerary={itinerary}
              onItineraryUpdate={setItinerary}
              onSashaResponse={handleSashaResponse}
              onListeningChange={setIsListening}
            />
          </div>
        </div>

        {/* RIGHT COLUMN — Itinerary */}
        <div className="flex-1 rounded-3xl border border-white/5 overflow-hidden" style={{ background: 'rgba(255,255,255,0.02)' }}>
          <ItineraryPanel
            itinerary={itinerary}
            user={DEMO_USER}
            onPay={(method) => setPaymentModal(method)}
          />
        </div>
      </div>

      {paymentModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="rounded-2xl p-6 w-96 shadow-xl" style={{ background: '#1a1a2e', border: '1px solid rgba(218,165,32,0.3)' }}>
            <div className="text-lg font-semibold mb-1" style={{ color: '#DAA520' }}>Complete Booking</div>
            <div className="text-sm mb-6" style={{ color: 'rgba(255,255,255,0.4)' }}>Total: ${itinerary.total_fiat.toLocaleString()}</div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setPaymentModal(null)} className="flex-1 py-3 rounded-xl text-sm" style={{ border: '1px solid rgba(218,165,32,0.2)', color: 'rgba(255,255,255,0.6)' }}>Cancel</button>
              <button className="flex-1 py-3 rounded-xl text-sm font-medium" style={{ background: 'linear-gradient(135deg, #DAA520, #B8860B)', color: 'white' }}>Confirm</button>
            </div>
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
      `}</style>
    </main>
  )
}
