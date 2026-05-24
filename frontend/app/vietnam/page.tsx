'use client'

import { useState, useCallback } from 'react'
import SashaAvatar from '../components/SashaAvatar'
import SashaChat from '../components/SashaChat'
import ItineraryPanel from '../components/ItineraryPanel'
import { User, Itinerary } from '@/types'

const DEMO_USER: User = {
  display_name: 'Alex',
  email: 'alex@example.com',
  default_currency: 'USD',
  sasha_context: 'Alex loves cultural immersion and authentic food experiences. Interested in a mix of adventure and luxury across Vietnam.',
  travellers: [
    { relation: 'self', first_name: 'Alex' },
    { relation: 'partner', first_name: 'Maya' },
  ],
  preferences: [
    { key: 'accommodation.type', value: 'boutique_heritage', source: 'explicit', confidence: 1.0, is_active: true },
    { key: 'experience.type', value: 'culture_and_food', source: 'explicit', confidence: 1.0, is_active: true },
  ],
  past_trips: [
    { title: 'Thailand — Chiang Mai and Bangkok', return_date: 'Mar 2025' },
    { title: 'Japan — Kyoto and Tokyo', return_date: 'Oct 2024' },
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

export default function VietnamPage() {
  const [itinerary, setItinerary] = useState<Itinerary>(INITIAL_ITINERARY)
  const [speakFn, setSpeakFn] = useState<((text: string) => void) | null>(null)
  const [isListening, setIsListening] = useState(false)
  const [paymentModal, setPaymentModal] = useState<'card' | 'crypto' | null>(null)

  const handleAvatarReady = useCallback((speak: (text: string) => void) => {
    setSpeakFn(() => speak)
  }, [])

  const handleSashaResponse = useCallback((text: string) => {
    if (speakFn) speakFn(text)
  }, [speakFn])

  return (
    <main className="h-screen flex flex-col overflow-hidden" style={{ background: '#0a0a0f' }}>
      {/* Vietnam branded top bar */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-white/5" style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(10px)' }}>
        <div className="flex items-center gap-3">
          <span className="text-xl">🇻🇳</span>
          <span className="text-white font-bold tracking-wide" style={{ color: '#DAA520' }}>Discover Vietnam</span>
          <div className="w-px h-4 bg-white/10" />
          <span className="text-xs text-white/30 tracking-widest uppercase">AI Travel Concierge</span>
        </div>
        <div className="text-xs px-3 py-1 rounded-full border" style={{ color: '#DAA520', borderColor: 'rgba(218,165,32,0.3)', background: 'rgba(218,165,32,0.1)' }}>
          Ministry of Tourism Partner
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 grid grid-cols-[1fr_380px_380px] gap-4 p-4 overflow-hidden">
        
        {/* Avatar with Vietnam video background */}
        <div className="relative rounded-3xl overflow-hidden border border-white/5">
          {/* Looping Vietnam background video */}
          <video
            autoPlay
            loop
            muted
            playsInline
            className="absolute inset-0 w-full h-full object-cover"
            style={{ opacity: 0.4 }}
          >
            <source src="https://videos.pexels.com/video-files/2169880/2169880-hd_1920_1080_30fps.mp4" type="video/mp4" />
          </video>
          {/* Dark overlay */}
          <div className="absolute inset-0" style={{ background: 'linear-gradient(to bottom, rgba(0,0,0,0.3), rgba(0,0,0,0.6))' }} />
          {/* Avatar on top */}
          <div className="relative z-10 w-full h-full">
            <SashaAvatar onAvatarReady={handleAvatarReady} isListening={isListening} />
          </div>
        </div>

        <SashaChat
          user={DEMO_USER}
          itinerary={itinerary}
          onItineraryUpdate={setItinerary}
          onSashaResponse={handleSashaResponse}
          onListeningChange={setIsListening}
        />
        <ItineraryPanel itinerary={itinerary} user={DEMO_USER} onPay={(method) => setPaymentModal(method)} />
      </div>

      {paymentModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="rounded-2xl p-6 w-96 shadow-xl" styl
