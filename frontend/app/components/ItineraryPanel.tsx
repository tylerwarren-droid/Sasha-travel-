'use client'

import { useState } from 'react'
import { Plane, Hotel, Anchor, Zap, ChevronRight, CreditCard, Bitcoin } from 'lucide-react'
import { Itinerary, ItineraryItem } from '@/types'

interface ItineraryPanelProps {
  itinerary: Itinerary
  user: any
  onPay: (method: 'card' | 'crypto') => void
}

const itemIcons: any = {
  flight: { icon: Plane, bg: 'bg-blue-50', color: 'text-blue-600' },
  hotel: { icon: Hotel, bg: 'bg-emerald-50', color: 'text-emerald-600' },
  transfer: { icon: Anchor, bg: 'bg-emerald-50', color: 'text-emerald-600' },
  activity: { icon: Zap, bg: 'bg-amber-50', color: 'text-amber-600' },
}

function ItemRow({ item }: { item: ItineraryItem }) {
  const [expanded, setExpanded] = useState(false)
  const iconConfig = itemIcons[item.type] || itemIcons.activity
  const Icon = iconConfig.icon

  return (
    <div
      className="bg-white border border-gray-100 rounded-xl p-3 mb-2 cursor-pointer hover:border-gray-200 transition-colors"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start gap-3">
        <div className={`w-7 h-7 rounded-lg ${iconConfig.bg} flex items-center justify-center flex-shrink-0`}>
          <Icon className={`w-3.5 h-3.5 ${iconConfig.color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-gray-900 leading-tight">{item.display_name}</div>
          {item.detail?.depart_at && (
            <div className="text-xs text-gray-400 mt-0.5">{item.detail.depart_at}</div>
          )}
          {item.detail?.check_in && (
            <div className="text-xs text-gray-400 mt-0.5">{item.detail.check_in} → {item.detail.check_out}</div>
          )}
        </div>
        <div className="text-xs font-medium text-gray-900 flex-shrink-0">
          {item.price_fiat > 0 ? `£${item.price_fiat.toLocaleString()}` : 'incl.'}
        </div>
      </div>
      {expanded && item.sasha_rationale && (
        <div className="mt-2 ml-10 text-xs text-indigo-600 italic">
          {item.sasha_rationale}
        </div>
      )}
      {expanded && (
        <div className="mt-2 ml-10 flex gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            item.is_refundable
              ? 'bg-emerald-50 text-emerald-600'
              : 'bg-red-50 text-red-500'
          }`}>
            {item.is_refundable ? 'Refundable' : 'Non-refundable'}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-500 capitalize">
            {item.status}
          </span>
        </div>
      )}
    </div>
  )
}

export default function ItineraryPanel({ itinerary, user, onPay }: ItineraryPanelProps) {
  const [activeTab, setActiveTab] = useState<'itinerary' | 'preferences' | 'trips'>('itinerary')

  const tabs = [
    { id: 'itinerary', label: 'Itinerary' },
    { id: 'preferences', label: 'Preferences' },
    { id: 'trips', label: 'Past trips' },
  ]

  return (
    <div className="flex flex-col h-full bg-gray-50 rounded-2xl border border-gray-100 overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-gray-100 bg-white">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex-1 py-3 text-xs font-medium transition-colors border-b-2 ${
              activeTab === tab.id
                ? 'text-indigo-600 border-indigo-600'
                : 'text-gray-400 border-transparent hover:text-gray-600'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Itinerary Tab */}
      {activeTab === 'itinerary' && (
        <div className="flex-1 overflow-y-auto p-3">
          <div className="mb-3">
            <div className="text-sm font-semibold text-gray-900">{itinerary.title}</div>
            <div className="text-xs text-gray-400 mt-0.5">
              {itinerary.depart_date && itinerary.return_date
                ? `${itinerary.depart_date} – ${itinerary.return_date}`
                : 'Dates TBC'
              } · {user.travellers?.length || 1} travellers
            </div>
          </div>

          {itinerary.items.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-3xl mb-3">✈️</div>
              <div className="text-sm text-gray-400">
                Your itinerary will build here as you chat with Sasha
              </div>
            </div>
          ) : (
            itinerary.items.map((item, i) => (
              <ItemRow key={i} item={item} />
            ))
          )}
        </div>
      )}

      {/* Preferences Tab */}
      {activeTab === 'preferences' && (
        <div className="flex-1 overflow-y-auto p-3">
          <div className="text-xs font-medium text-gray-400 mb-3">
            Sasha has learned these across your trips
          </div>
          <div className="flex flex-wrap gap-2">
            {user.preferences?.map((pref: any, i: number) => (
              <span key={i} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs bg-white border border-gray-100 text-gray-600">
                <span className={`w-1.5 h-1.5 rounded-full ${
                  pref.confidence >= 1.0 ? 'bg-emerald-500' : 'bg-amber-400'
                }`}></span>
                {pref.key.replace('.', ' › ')} : {String(pref.value)}
              </span>
            ))}
            {(!user.preferences || user.preferences.length === 0) && (
              <div className="text-sm text-gray-400 py-8 text-center w-full">
                Preferences will appear here as Sasha learns how you travel
              </div>
            )}
          </div>
        </div>
      )}

      {/* Past Trips Tab */}
      {activeTab === 'trips' && (
        <div className="flex-1 overflow-y-auto p-3">
          <div className="text-xs font-medium text-gray-400 mb-3">Previous trips</div>
          {user.past_trips?.map((trip: any, i: number) => (
            <div key={i} className="bg-white border border-gray-100 rounded-xl p-3 mb-2 flex items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-emerald-50 flex items-center justify-center text-sm">
                🌴
              </div>
              <div>
                <div className="text-xs font-medium text-gray-900">{trip.title}</div>
                <div className="text-xs text-gray-400">{trip.return_date}</div>
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-gray-300 ml-auto" />
            </div>
          ))}
          {(!user.past_trips || user.past_trips.length === 0) && (
            <div className="text-sm text-gray-400 py-8 text-center">
              Your completed trips will appear here
            </div>
          )}
        </div>
      )}

      {/* Payment Bar */}
      {activeTab === 'itinerary' && (
        <div className="p-3 border-t border-gray-100 bg-white">
          <div className="flex justify-between items-center mb-2.5">
            <span className="text-xs text-gray-400">Trip total</span>
            <span className="text-lg font-semibold text-gray-900">
              £{itinerary.total_fiat.toLocaleString()}
            </span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => onPay('card')}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-medium transition-colors"
            >
              <CreditCard className="w-3.5 h-3.5" />
              Pay by card
            </button>
            <button
              onClick={() => onPay('crypto')}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-gray-50 hover:bg-gray-100 text-gray-700 border border-gray-200 rounded-xl text-xs font-medium transition-colors"
            >
              <Bitcoin className="w-3.5 h-3.5" />
              Pay crypto
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
