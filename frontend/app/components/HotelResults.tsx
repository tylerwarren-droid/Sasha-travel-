'use client'

import { useState } from 'react'
import HotelCard from './HotelCard'

interface HotelResultsProps {
  hotels: any[]
  onSelect: (hotel: any) => void
}

export default function HotelResults({ hotels, onSelect }: HotelResultsProps) {
  const [selected, setSelected] = useState<string | null>(null)

  const handleSelect = (hotel: any) => {
    setSelected(hotel.id)
    onSelect(hotel)
  }

  if (!hotels || hotels.length === 0) return null

  return (
    <div className="mt-3">
      <div className="text-xs text-gray-400 mb-2">
        {hotels.length} options — tap to select
      </div>
      <div className="grid grid-cols-3 gap-2">
        {hotels.slice(0, 3).map((hotel, i) => (
          <HotelCard
            key={hotel.id || i}
            hotel={hotel}
            onSelect={handleSelect}
            selected={selected === hotel.id}
          />
        ))}
      </div>
    </div>
  )
}
