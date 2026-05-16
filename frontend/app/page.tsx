'use client'

import { useState } from 'react'
import SashaChat from './components/SashaChat'
import ItineraryPanel from './components/ItineraryPanel'
import { User, Itinerary } from '@/types'

// Demo user — this will come from auth in production
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
    { key: 'payment.method', value: 'card', source: 'inferred', confidence: 0.7, is_active: true },
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
  const [paymentModal, setPaymentModal] = useState<'card' | 'crypto' | null>(null)

  const handlePay = (method: 'card' | 'crypto') => {
    setPaymentModal(method)
  }

  return (
    <main className="h-screen bg-gray-50 flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="text-lg font-semibold text-indigo-600 tracking-tight">Sasha</div>
          <div className="text-xs text-gray-300">|</div>
          <div className="text-xs text-gray-400">AI Travel</div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-gray-500">{DEMO_USER.display_name}</div>
          <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-xs font-medium text-indigo-600">
            {DEMO_USER.display_name[0]}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 grid grid-cols-[1fr_360px] gap-4 p-4 overflow-hidden">
        <SashaChat
          user={DEMO_USER}
          itinerary={itinerary}
          onItineraryUpdate={setItinerary}
        />
        <ItineraryPanel
          itinerary={itinerary}
          user={DEMO_USER}
          onPay={handlePay}
        />
      </div>

      {/* Payment Modal */}
      {paymentModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-96 shadow-xl">
            <div className="text-lg font-semibold text-gray-900 mb-1">
              {paymentModal === 'card' ? 'Pay by card' : 'Pay with crypto'}
            </div>
            <div className="text-sm text-gray-400 mb-6">
              Total: £{itinerary.total_fiat.toLocaleString()}
            </div>
            {paymentModal === 'card' ? (
              <div className="space-y-3">
                <input placeholder="Card number" className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm outline-none focus:border-indigo-300" />
                <div className="grid grid-cols-2 gap-3">
                  <input placeholder="MM/YY" className="border border-gray-200 rounded-xl px-4 py-3 text-sm outline-none focus:border-indigo-300" />
                  <input placeholder="CVC" className="border border-gray-200 rounded-xl px-4 py-3 text-sm outline-none focus:border-indigo-300" />
                </div>
              </div>
            ) : (
              <div className="text-center py-4">
                <div className="text-4xl mb-3">₿</div>
                <div className="text-sm text-gray-500">Crypto payment coming soon</div>
              </div>
            )}
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setPaymentModal(null)}
                className="flex-1 py-3 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button className="flex-1 py-3 bg-indigo-600 rounded-xl text-sm text-white font-medium hover:bg-indigo-700">
                Confirm payment
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
