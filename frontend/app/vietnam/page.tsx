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
  const [rightTab, setRightTab] = useState<'chat' | 'itinerary'>('chat')
  const photoInterval = useRef<any>(null)

  useEffect(() => {
    const fetchPhotos = async () => {
      try {
        const res = await fetch('https://sasha-travel-production.up.railway.app/api/photos/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: photoQuery, count: 5 })
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

  const handleItineraryUpdate = useCallback((newItinerary: Itinerary) => {
    setItinerary(newItinerary)
    if (newItinerary.items?.length > 0) {
      setRightTab('itinerary')
    }
  }, [])

  return (
    <main className="h-screen flex flex-col overflow-hidden" style={{ background: '#080810' }}>

      {/* HEADER */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/5 flex-shrink-0" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(10px)' }}>
        <div className="flex items-center gap-2">
          <span className="text-lg">🇻🇳</span>
          <span className="font-bold tracking-wide text-sm" style={{ color: '#DAA520' }}>Discover Vietnam</span>
          <div className="w-px h-3 bg-white/10" />
          <span className="text-xs text-white/30 tracking-widest uppercase hidden sm:block">AI Travel Concierge</span>
        </div>
        <div className="text-xs px-2 py-1 rounded-full border" style={{ color: '#DAA520', borderColor: 'rgba(218,165,32,0.3)', background: 'rgba(218,165,32,0.1)' }}>
          MoT Partner
        </div>
      </div>

      {/* MIDDLE — Avatar + Chat/Itinerary side by side */}
      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>

        {/* LEFT — Avatar */}
        <div className="flex-shrink-0 overflow-hidden border-r border-white/5" style={{ width: '38%' }}>
          <SashaAvatar onAvatarReady={handleAvatarReady} isListening={isListening} />
        </div>

        {/* RIGHT — Chat OR Itinerary, same input bar always visible */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* Two tabs: Chat / Itinerary */}
          <div className="flex border-b border-white/5 flex-shrink-0">
            <button
              onClick={() => setRightTab('chat')}
              className="flex-1 py-2.5 text-xs font-medium transition-all"
              style={{
                color: rightTab === 'chat' ? '#DAA520' : 'rgba(255,255,255,0.3)',
                borderBottom: rightTab === 'chat' ? '2px solid #DAA520' : '2px solid transparent'
              }}
            >
              💬 Sasha
            </button>
            <button
              onClick={() => setRightTab('itinerary')}
              className="flex-1 py-2.5 text-xs font-medium transition-all relative"
              style={{
                color: rightTab === 'itinerary' ? '#DAA520' : 'rgba(255,255,255,0.3)',
                borderBottom: rightTab === 'itinerary' ? '2px solid #DAA520' : '2px solid transparent'
              }}
            >
              🗺️ Itinerary
              {itinerary.items?.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full" style={{ background: '#DAA520', color: '#000', fontSize: '9px' }}>
                  {itinerary.items.length}
                </span>
              )}
            </button>
          </div>

          {/* Content area — chat messages OR itinerary cards */}
          <div className="flex-1 overflow-hidden">
            {rightTab === 'chat' ? (
              <SashaChat
                user={DEMO_USER}
                itinerary={itinerary}
                onItineraryUpdate={handleItineraryUpdate}
                onSashaResponse={handleSashaResponse}
                onListeningChange={setIsListening}
              />
            ) : (
              <div className="flex flex-col h-full">
                {/* Itinerary cards — scrollable */}
                <div className="flex-1 overflow-y-auto">
                  <ItineraryPanel
                    itinerary={itinerary}
                    user={DEMO_USER}
                    onPay={(method) => setPaymentModal(method)}
                  />
                </div>
                {/* Same input bar so you can still talk to Sasha */}
                <div className="px-3 pb-3 pt-2 border-t border-white/5 flex-shrink-0">
                  <SashaChat
                    user={DEMO_USER}
                    itinerary={itinerary}
                    onItineraryUpdate={handleItineraryUpdate}
                    onSashaResponse={handleSashaResponse}
                    onListeningChange={setIsListening}
                    inputOnly={true}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* BOTTOM — Full width photo strip */}
      <div className="flex-shrink-0 border-t border-white/5 overflow-hidden" style={{ height: '110px', background: 'rgba(0,0,0,0.4)' }}>
        {photos.length > 0 ? (
          <div className="flex h-full gap-1 p-1">
            {photos.map((photo, i) => (
              <button
                key={i}
                onClick={() => setActivePhoto(i)}
                className="relative flex-1 rounded-xl overflow-hidden transition-all duration-300"
                style={{
                  border: i === activePhoto ? '2px solid #DAA520' : '2px solid transparent',
                  flex: i === activePhoto ? '2' : '1'
                }}
              >
                <img
                  src={photo.thumb}
                  alt={photo.description}
                  className="w-full h-full object-cover"
                  style={{ opacity: i === activePhoto ? 1 : 0.5 }}
                />
                {i === activePhoto && (
                  <div className="absolute bottom-1 left-1 right-1">
                    <div className="text-white/60 text-xs truncate px-1">📷 {photo.photographer}</div>
                  </div>
                )}
              </button>
            ))}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <div className="text-white/20 text-xs">Loading photos...</div>
          </div>
        )}
      </div>

      {/* Payment modal */}
      {paymentModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="rounded-2xl p-6 w-80 shadow-xl" style={{ background: '#1a1a2e', border: '1px solid rgba(218,165,32,0.3)' }}>
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
