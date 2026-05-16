'use client'

import { useState } from 'react'
import { Star, MapPin, Wifi, Coffee, Waves } from 'lucide-react'

interface HotelCardProps {
  hotel: {
    id: string
    name: string
    stars: number
    location: string
    price: number
    currency: string
    image_url?: string
    amenities?: string[]
    rationale?: string
  }
  onSelect: (hotel: any) => void
  selected?: boolean
}

const amenityIcons: any = {
  pool: Waves,
  wifi: Wifi,
  breakfast: Coffee,
}

export default function HotelCard({ hotel, onSelect, selected }: HotelCardProps) {
  const [imageError, setImageError] = useState(false)

  const emojis: any = {
    5: '🏝️',
    4: '🌴',
    3: '🏨',
  }

  return (
    <div
      onClick={() => onSelect(hotel)}
      className={`rounded-xl overflow-hidden border cursor-pointer transition-all hover:shadow-md ${
        selected
          ? 'border-indigo-500 ring-1 ring-indigo-500'
          : 'border-gray-100 hover:border-gray-200'
      }`}
    >
      <div className="w-full h-32 bg-gradient-to-br from-indigo-50 to-emerald-50 flex items-center justify-center text-4xl">
        {emojis[hotel.stars] || '🏨'}
      </div>
      <div className="p-3 bg-white">
        <div className="flex items-start justify-between gap-2">
          <div className="font-medium text-gray-900 text-xs leading-tight">{hotel.name}</div>
          <div className="text-xs font-semibold text-indigo-600 whitespace-nowrap">
            £{hotel.price.toLocaleString()}
          </div>
        </div>
        <div className="flex items-center gap-1 mt-1">
          {Array.from({ length: hotel.stars }).map((_, i) => (
            <Star key={i} className="w-2.5 h-2.5 fill-amber-400 text-amber-400" />
          ))}
        </div>
        <div className="flex items-center gap-1 mt-1.5">
          <MapPin className="w-2.5 h-2.5 text-gray-300 flex-shrink-0" />
          <span className="text-xs text-gray-400 truncate">{hotel.location}</span>
        </div>
        {hotel.rationale && (
          <div className="mt-2 text-xs text-indigo-500 italic leading-tight">
            {hotel.rationale}
          </div>
        )}
        {selected && (
          <div className="mt-2 bg-indigo-50 text-indigo-600 text-xs px-2 py-1 rounded-lg text-center font-medium">
            Selected ✓
          </div>
        )}
      </div>
    </div>
  )
}
