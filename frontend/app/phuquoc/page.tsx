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
  sasha_context: 'Alex is exploring Phu Quoc ahead of APEC 2027. Interested in luxury beach resorts, spa, golf at Vinpearl, and getting ahead of the crowd before prices spike.',
  travellers: [
    { relation: 'self', first_name: 'Alex' },
    { relation: 'partner', first_name: 'Maya' },
  ],
  preferences: [
    { key: 'accommodation.type', value: 'boutique_heritage', source: 'explicit', confidence: 1.0, is_active: true },
    { key: 'experience.type', value: 'culture_and_food', source: 'explicit', confidence: 1.0, is_active: true },
  ],
  past_trips: [
    
    { title: 'Bali — Seminyak and Ubud', return_date: 'Winter 2023' },
  ],
  ota_affinity: ['culture', 'adventure']
}

const INITIAL_ITINERARY: Itinerary = {
  title: 'Phu Quoc Discovery',
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

export default function PhuQuocPage() {
  const [itinerary, setItinerary] = useState<Itinerary>(INITIAL_ITINERARY)
  const [speakFn, setSpeakFn] = useState<((text: string) => void) | null>(null)
  const [isListening, setIsListening] = useState(false)
  const [paymentModal, setPaymentModal] = useState<'card' | 'crypto' | null>(null)
  const [photos, setPhotos] = useState<Photo[]>([])
  const [activePhoto, setActivePhoto] = useState(0)
  const [photoQuery, setPhotoQuery] = useState('Phu Quoc island beach luxury Vietnam')
  const [engaged, setEngaged] = useState(false)
  const [rightTab, setRightTab] = useState<'chat' | 'itinerary' | 'preferences' | 'trips'>('chat')
  const [started, setStarted] = useState(false)
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

  const hasSpoken = useRef(false)
  const handleAvatarReady = useCallback((speak: (text: string) => void) => {
    setSpeakFn(() => speak)
    if (!hasSpoken.current) {
      hasSpoken.current = true
      setTimeout(() => speak(`Phu Quoc has just been named the APEC 2027 host. Vietnam's first LRT, a new airport terminal, and Sun Group's luxury hotel city are all under construction. Prices are still pre-APEC. Shall I show you what Phu Quoc looks like before the world catches on?`), 200)
    }
  }, [])

  const handleSashaResponse = useCallback((text: string) => {
    if (speakFn) speakFn(text)
    setEngaged(true)
    const lower = text.toLowerCase()
    const golfCourses = ['vinpearl golf', 'phu quoc golf']
    const destinations = ['long beach', 'sao beach', 'bai dai', 'grand world', 'sun world', 'vinpearl', 'duong dong', 'phu quoc', 'pearl island', 'apec', 'yes', 'show me', 'tell me more']
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
      <div className="flex items-center justify-between px-6 py-3 border-b border-white/5 flex-shrink-0" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(10px)' }}>
        <div className="flex items-center gap-3">
          <span className="text-xl">🏝️</span>
          <span className="font-bold tracking-wide" style={{ color: '#00B4D8' }}>Discover Phu Quoc</span>
          <div className="w-px h-4 bg-white/10" />
          <span className="text-xs text-white/30 tracking-widest uppercase">AI Travel Concierge</span>
        </div>
        <div className="text-xs px-3 py-1 rounded-full border" style={{ color: '#00B4D8', borderColor: 'rgba(0,180,216,0.3)', background: 'rgba(0,180,216,0.1)' }}>
          🌏 APEC 2027 Host
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div className="flex-1 flex overflow-hidden p-2 gap-2" style={{ minHeight: 0 }}>

        {/* LEFT COLUMN — Avatar + Photos */}
        <div className="flex flex-col gap-3 overflow-hidden" style={{ width: '42%' }}>

          {/* AVATAR — big on landing, small when engaged */}
          <div
            className="rounded-3xl overflow-hidden border border-white/5 flex-shrink-0 transition-all duration-700"
            style={{ height: engaged ? '160px' : '60%' }}
          >
            {started && <SashaAvatar onAvatarReady={handleAvatarReady} isListening={isListening} tokenUrl="/api/heygen/token/phuquoc" />}
          </div>

          {/* PHOTOS — hero when engaged, teaser when not */}
          <div
            className="relative rounded-3xl overflow-hidden border border-white/5 transition-all duration-700"
            style={{ flex: 1, minHeight: 0 }}
          >
            {photos.length > 0 ? (
              <>
                <img
                  key={activePhoto}
                  src={photos[activePhoto]?.url}
                  alt={photos[activePhoto]?.description}
                  className="w-full h-full object-cover transition-opacity duration-500"
                  style={{ opacity: engaged ? 1 : 0.4, animation: 'fadeIn 0.8s ease' }}
                />
                <div className="absolute inset-0" style={{ background: 'linear-gradient(to bottom, transparent 50%, rgba(0,0,0,0.8) 100%)' }} />

                {/* Welcome overlay */}
                {!engaged && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="text-white/40 text-xs tracking-widest uppercase">Start talking to explore Phu Quoc</div>
                  </div>
                )}

                {/* Engaged: caption + controls */}
                {engaged && (
                  <>
                    <div className="absolute bottom-3 left-4">
                      <div className="text-white/50 text-xs">📷 {photos[activePhoto]?.photographer}</div>
                    </div>
                    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5">
                      {photos.map((_, i) => (
                        <button key={i} onClick={() => setActivePhoto(i)}
                          className="rounded-full transition-all"
                          style={{ width: i === activePhoto ? '18px' : '6px', height: '6px', background: i === activePhoto ? '#00B4D8' : 'rgba(255,255,255,0.3)' }}
                        />
                      ))}
                    </div>
                    <div className="absolute top-3 right-3 flex gap-1.5">
                      {photos.map((p, i) => (
                        <button key={i} onClick={() => setActivePhoto(i)}
                          className="rounded-lg overflow-hidden border-2 transition-all"
                          style={{ width: '44px', height: '32px', borderColor: i === activePhoto ? '#00B4D8' : 'rgba(255,255,255,0.2)' }}
                        >
                          <img src={p.thumb} alt="" className="w-full h-full object-cover" />
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </>
            ) : (
              <div className="w-full h-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #0a0a1a, #1a1a3a)' }}>
                <div className="text-white/20 text-sm">🏝️</div>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN — Tabs: Chat / Itinerary / Preferences / Past Trips */}
        <div className="flex-1 flex flex-col rounded-3xl border border-white/5 overflow-hidden" style={{ background: 'rgba(255,255,255,0.02)', minWidth: '280px' }}>

          {/* Tab bar */}
          <div className="flex border-b border-white/5 flex-shrink-0">
            {[
              { key: 'chat', label: 'Sasha' },
              { key: 'itinerary', label: 'Itinerary', badge: itinerary.items?.length || 0 },
              { key: 'preferences', label: 'Prefs' },
              { key: 'trips', label: 'Trips' },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setRightTab(tab.key as any)}
                className="flex-1 py-2.5 text-xs transition-all relative"
                style={{
                  color: rightTab === tab.key ? '#00B4D8' : 'rgba(255,255,255,0.3)',
                  borderBottom: rightTab === tab.key ? '2px solid #DAA520' : '2px solid transparent'
                }}
              >
                {tab.label}
                {tab.badge ? (
                  <span className="ml-1 px-1.5 py-0.5 rounded-full text-xs" style={{ background: '#00B4D8', color: '#000', fontSize: '10px' }}>
                    {tab.badge}
                  </span>
                ) : null}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-hidden">

            {/* CHAT TAB */}
            {rightTab === 'chat' && (
              <SashaChat
                user={DEMO_USER}
                itinerary={itinerary}
                onItineraryUpdate={handleItineraryUpdate}
                onSashaResponse={handleSashaResponse}
                onListeningChange={setIsListening}
                initialMessage={`🏝️ Phu Quoc has just been named the APEC 2027 host. Vietnam's first LRT, a new airport terminal, and Sun Group's luxury hotel city are all under construction. Prices are still pre-APEC. Shall I show you what Phu Quoc looks like before the world catches on? 🌏`}
              />
            )}

            {/* ITINERARY TAB */}
            {rightTab === 'itinerary' && (
              <ItineraryPanel
                itinerary={itinerary}
                user={DEMO_USER}
                onPay={(method) => setPaymentModal(method)}
              />
            )}

            {/* PREFERENCES TAB */}
            {rightTab === 'preferences' && (
              <div className="p-6 space-y-4 overflow-y-auto h-full">
                <div className="text-sm font-medium text-white/60 mb-4">Travel Preferences</div>
                {DEMO_USER.preferences?.map((pref, i) => (
                  <div key={i} className="rounded-xl p-4 border border-white/5" style={{ background: 'rgba(255,255,255,0.03)' }}>
                    <div className="text-xs text-white/30 mb-1">{pref.key.replace('.', ' › ')}</div>
                    <div className="text-sm text-white/70 capitalize">{pref.value.replace(/_/g, ' ')}</div>
                  </div>
                ))}
                <div className="rounded-xl p-4 border border-white/5" style={{ background: 'rgba(255,255,255,0.03)' }}>
                  <div className="text-xs text-white/30 mb-1">Travellers</div>
                  <div className="text-sm text-white/70">{DEMO_USER.travellers?.map(t => `${t.first_name} (${t.relation})`).join(', ')}</div>
                </div>
              </div>
            )}

            {/* PAST TRIPS TAB */}
            {rightTab === 'trips' && (
              <div className="p-6 space-y-4 overflow-y-auto h-full">
                <div className="text-sm font-medium text-white/60 mb-4">Past Trips</div>
                {DEMO_USER.past_trips?.map((trip, i) => (
                  <div key={i} className="rounded-xl p-4 border border-white/5" style={{ background: 'rgba(255,255,255,0.03)' }}>
                    <div className="text-sm text-white/70">{trip.title}</div>
                    <div className="text-xs text-white/30 mt-1">{trip.return_date}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {paymentModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="rounded-2xl p-6 w-96 shadow-xl" style={{ background: '#1a1a2e', border: '1px solid rgba(0,180,216,0.3)' }}>
            <div className="text-lg font-semibold mb-1" style={{ color: '#00B4D8' }}>Complete Booking</div>
            <div className="text-sm mb-6" style={{ color: 'rgba(255,255,255,0.4)' }}>Total: ${itinerary.total_fiat.toLocaleString()}</div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setPaymentModal(null)} className="flex-1 py-3 rounded-xl text-sm" style={{ border: '1px solid rgba(0,180,216,0.2)', color: 'rgba(255,255,255,0.6)' }}>Cancel</button>
              <button className="flex-1 py-3 rounded-xl text-sm font-medium" style={{ background: 'linear-gradient(135deg, #DAA520, #0077B6)', color: 'white' }}>Confirm</button>
            </div>
          </div>
        </div>
      )}

      {/* Tap-to-start overlay — gates audio init until user gesture */}
      {!started && (
        <div
          className="fixed inset-0 z-50 flex flex-col items-center justify-center cursor-pointer select-none"
          style={{ background: 'rgba(8,8,16,0.96)', backdropFilter: 'blur(10px)' }}
          onClick={() => setStarted(true)}
        >
          <div style={{ fontSize: '52px', marginBottom: '20px' }}>🏝️</div>
          <div style={{ fontFamily: 'system-ui,sans-serif', fontSize: '26px', fontWeight: 700, color: '#00B4D8', marginBottom: '8px', letterSpacing: '-0.3px' }}>
            Discover Phu Quoc
          </div>
          <div style={{ fontSize: '13px', color: 'rgba(255,255,255,0.35)', marginBottom: '44px', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            AI Travel Concierge · APEC 2027 Host
          </div>
          <div
            style={{
              display: 'flex', alignItems: 'center', gap: '12px',
              padding: '16px 36px', borderRadius: '16px', fontSize: '16px', fontWeight: 700,
              background: 'linear-gradient(135deg, #00B4D8, #0077B6)', color: '#fff',
              boxShadow: '0 8px 32px rgba(0,180,216,0.35)',
              animation: 'pulse 2s ease-in-out infinite',
            }}
          >
            <span style={{ fontSize: '18px' }}>▶</span> Tap to start
          </div>
          <div style={{ marginTop: '16px', fontSize: '12px', color: 'rgba(255,255,255,0.2)' }}>
            Audio plays automatically once you start
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
        @keyframes pulse {
          0%, 100% { box-shadow: 0 8px 32px rgba(0,180,216,0.35); }
          50% { box-shadow: 0 8px 48px rgba(0,180,216,0.6); }
        }
      `}</style>
    </main>
  )
}
