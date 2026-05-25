'use client'

import { useState, useCallback, useEffect } from 'react'
import SashaAvatar from '../components/SashaAvatar'
import SashaChat from '../components/SashaChat'
import FotoStrip from '../components/FotoStrip'
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


const VIETNAM_VIDEOS = [
  'https://videos.pexels.com/video-files/2169880/2169880-hd_1920_1080_30fps.mp4',
  'https://videos.pexels.com/video-files/3752847/3752847-hd_1920_1080_25fps.mp4',
  'https://videos.pexels.com/video-files/4763824/4763824-hd_1920_1080_25fps.mp4',
  'https://videos.pexels.com/video-files/2098870/2098870-hd_1920_1080_30fps.mp4',
]

function CyclingBackground() {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [fade, setFade] = useState(true)

  useEffect(() => {
    const interval = setInterval(() => {
      setFade(false)
      setTimeout(() => {
        setCurrentIndex(prev => (prev + 1) % VIETNAM_VIDEOS.length)
        setFade(true)
      }, 1000)
    }, 8000)
    return () => clearInterval(interval)
  }, [])

  return (
    <video
      key={currentIndex}
      autoPlay
      loop
      muted
      playsInline
      className="absolute inset-0 w-full h-full object-cover"
      style={{ opacity: fade ? 0.5 : 0, transition: 'opacity 1s ease' }}
    >
      <source src={VIETNAM_VIDEOS[currentIndex]} type="video/mp4" />
    </video>
  )
}

export default function VietnamPage() {
  const [itinerary, setItinerary] = useState<Itinerary>(INITIAL_ITINERARY)
  const [speakFn, setSpeakFn] = useState<((text: string) => void) | null>(null)
  const [isListening, setIsListening] = useState(false)
  const [fotoQuery, setFotoQuery] = useState<{query: string, type: string} | null>(null)
  const [paymentModal, setPaymentModal] = useState<'card' | 'crypto' | null>(null)

  const handleAvatarReady = useCallback((speak: (text: string) => void) => {
    setSpeakFn(() => speak)
  }, [])

  const handleSashaResponse = useCallback((text: string) => {
    if (speakFn) speakFn(text)
  }, [speakFn])

  return (
    <main className="h-screen flex flex-col overflow-hidden" style={{ background: '#0a0a0f' }}>
      <div className="flex items-center justify-between px-6 py-3 border-b border-white/5" style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(10px)' }}>
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

      <div className="flex-1 grid grid-cols-1 md:grid-cols-[1fr_380px_380px] gap-4 p-4 overflow-hidden">
        <div className="hidden md:block relative rounded-3xl overflow-hidden border border-white/5 bg-black">
          {/* Cycling Vietnam background videos */}
          <CyclingBackground />
          {/* Avatar with transparent green screen on top */}
          <div className="absolute inset-0 z-10">
            <SashaAvatar onAvatarReady={handleAvatarReady} isListening={isListening} />
          </div>
        </div>
        <SashaChat
          user={DEMO_USER}
          itinerary={itinerary}
          onItineraryUpdate={setItinerary}
          onSashaResponse={handleSashaResponse}
          onFotoQuery={setFotoQuery}
          onListeningChange={setIsListening}
        />
        <div className="hidden md:block flex flex-col gap-3"><FotoStrip query={fotoQuery?.query || 'Vietnam'} type={fotoQuery?.type || 'destination'} visible={true} /><ItineraryPanel itinerary={itinerary} user={DEMO_USER} onPay={(method) => setPaymentModal(method)} /></div>
      </div>

      {paymentModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="rounded-2xl p-6 w-96 shadow-xl" style={{ background: '#1a1a2e', border: '1px solid rgba(218,165,32,0.3)' }}>
            <div className="text-lg font-semibold mb-1" style={{ color: '#DAA520' }}>Complete Booking</div>
            <div className="text-sm mb-6" style={{ color: 'rgba(255,255,255,0.4)' }}>Total: ${itinerary.total_fiat.toLocaleString()}</div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setPaymentModal(null)} className="flex-1 py-3 rounded-xl text-sm" style={{ border: '1px solid rgba(218,165,32,0.2)', color: 'rgba(255,255,255,0.6)' }}>Cancel</button>
              <button className="flex-1 py-3 rounded-xl text-sm font-medium" style={{ background: 'linear-gradient(135deg, #DAA520, #B8860B)', color: 'white' }}>Confirm Booking</button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
// deploy Sun May 24 16:49:18 CEST 2026
