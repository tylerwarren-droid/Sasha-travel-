'use client'

import { useState, useCallback } from 'react'
import SashaAvatar from './components/SashaAvatar'
import SashaChat from './components/SashaChat'
import ItineraryPanel from './components/ItineraryPanel'
import { User, Itinerary } from '@/types'

const DEMO_USER: User = {
  display_name: 'Jon',
  email: 'jon@example.com',
  default_currency: 'GBP',
  sasha_context: 'Jon travels with his wife and 2 kids aged 8 and 11. Prefers 5-star beach resorts. No red-eye flights. Loves overwater villas.',
  travellers: [
    { relation: 'self', first_name: 'Jon' },
    { relation: 'partner', first_name: 'Sarah' },
    { relation: 'child', first_name: 'Emma', date_of_birth: '2016-03-15' },
    { relation: 'child', first_name: 'Tom', date_of_birth: '2013-07-22' },
  ],
  preferences: [
    { key: 'flight.timing', value: 'daytime_only', source: 'explicit', confidence: 1.0, is_active: true },
    { key: 'accommodation.stars', value: 5, source: 'explicit', confidence: 1.0, is_active: true },
    { key: 'accommodation.type', value: 'overwater_villa', source: 'inferred', confidence: 0.85, is_active: true },
    { key: 'activity.kids', value: true, source: 'inferred', confidence: 0.9, is_active: true },
  ],
  past_trips: [
    { title: 'Seychelles — Fregate Island', return_date: 'May 2025' },
    { title: 'Amalfi Coast — Positano', return_date: 'Aug 2024' },
    { title: 'Kenya — Laikipia Safari', return_date: 'Dec 2023' },
  ],
  ota_affinity: ['beach', 'adventure']
}

const INITIAL_ITINERARY: Itinerary = {
  title: 'New trip',
  ota_channel: 'beach',
  status: 'draft',
  total_fiat: 0,
  items: []
}

export default function Home() {
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
    <main className="h-screen bg-[#0a0a0f] flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <span className="text-white font-bold text-xs">S</span>
            </div>
            <span className="text-white font-light tracking-[0.15em] text-sm">SASHA</span>
          </div>
          <div className="w-px h-4 bg-white/10" />
          <span className="text-xs text-white/20 tracking-widest uppercase">AI Travel</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-white/30">{DEMO_USER.display_name}</span>
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500/20 to-purple-600/20 border border-white/10 flex items-center justify-center text-xs font-medium text-white/60">
            {DEMO_USER.display_name[0]}
          </div>
        </div>
      </div>
      <div className="flex-1 grid grid-cols-[1fr_380px_380px] gap-4 p-4 overflow-hidden">
        <SashaAvatar onAvatarReady={handleAvatarReady} isListening={isListening} />
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
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-[#12121a] border border-white/10 rounded-3xl p-8 w-96 shadow-2xl">
            <div className="text-base font-light text-white mb-1">{paymentModal === 'card' ? 'Pay by card' : 'Pay with crypto'}</div>
            <div className="text-xs text-white/30 mb-8">Total: £{itinerary.total_fiat.toLocaleString()}</div>
            <div className="flex gap-3 mt-8">
              <button onClick={() => setPaymentModal(null)} className="flex-1 py-3 border border-white/10 rounded-2xl text-sm text-white/40">Cancel</button>
              <button className="flex-1 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-2xl text-sm text-white font-medium">Confirm</button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
