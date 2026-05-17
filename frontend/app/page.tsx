"use client"

import { useState } from "react"
import SashaChat from "./components/SashaChat"
import ItineraryPanel from "./components/ItineraryPanel"
import { User, Itinerary } from "@/types"

const DEMO_USER: User = {
  display_name: "Alex",
  email: "alex@example.com",
  default_currency: "USD",
  sasha_context: "Alex loves cultural immersion, authentic food experiences, and a mix of adventure and luxury.",
  travellers: [
    { relation: "self", first_name: "Alex" },
    { relation: "partner", first_name: "Maya" },
  ],
  preferences: [
    { key: "accommodation.type", value: "boutique_heritage", source: "explicit", confidence: 1.0, is_active: true },
    { key: "experience.type", value: "culture_and_food", source: "explicit", confidence: 1.0, is_active: true },
  ],
  past_trips: [
    { title: "Thailand — Chiang Mai and Bangkok", return_date: "Mar 2025" },
    { title: "Japan — Kyoto and Tokyo", return_date: "Oct 2024" },
  ],
  ota_affinity: ["culture", "adventure"]
}

const INITIAL_ITINERARY: Itinerary = {
  title: "Vietnam Discovery",
  ota_channel: "culture",
  status: "draft",
  total_fiat: 0,
  items: []
}

export default function Home() {
  const [itinerary, setItinerary] = useState<Itinerary>(INITIAL_ITINERARY)
  const [paymentModal, setPaymentModal] = useState<"card" | "crypto" | null>(null)

  return (
    <main className="h-screen flex flex-col" style={{ background: "linear-gradient(135deg, #0f1923 0%, #1a0a0a 50%, #0f1923 100%)" }}>
      <div className="flex items-center justify-between px-6 py-3 border-b" style={{ background: "rgba(0,0,0,0.4)", borderColor: "rgba(218,165,32,0.2)" }}>
        <div className="flex items-center gap-3">
          <span className="text-xl">🇻🇳</span>
          <div className="text-lg font-bold" style={{ color: "#DAA520" }}>Discover Vietnam</div>
          <div className="text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>|</div>
          <div className="text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>AI Travel Concierge</div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs px-3 py-1 rounded-full border" style={{ color: "#DAA520", borderColor: "rgba(218,165,32,0.3)", background: "rgba(218,165,32,0.1)" }}>
            Ministry of Tourism Partner
          </div>
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium" style={{ background: "rgba(218,165,32,0.2)", color: "#DAA520" }}>
            {DEMO_USER.display_name[0]}
          </div>
        </div>
      </div>

      <div className="flex-1 grid grid-cols-[1fr_360px] gap-4 p-4 overflow-hidden">
        <SashaChat user={DEMO_USER} itinerary={itinerary} onItineraryUpdate={setItinerary} />
        <ItineraryPanel itinerary={itinerary} user={DEMO_USER} onPay={(method) => setPaymentModal(method)} />
      </div>

      {paymentModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: "rgba(0,0,0,0.7)" }}>
          <div className="rounded-2xl p-6 w-96 shadow-xl" style={{ background: "#1a1a2e", border: "1px solid rgba(218,165,32,0.3)" }}>
            <div className="text-lg font-semibold mb-1" style={{ color: "#DAA520" }}>Complete Booking</div>
            <div className="text-sm mb-6" style={{ color: "rgba(255,255,255,0.4)" }}>Total: ${itinerary.total_fiat.toLocaleString()}</div>
            <input placeholder="Card number" className="w-full rounded-xl px-4 py-3 text-sm outline-none mb-3" style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(218,165,32,0.2)", color: "white" }} />
            <div className="flex gap-3 mt-3">
              <button onClick={() => setPaymentModal(null)} className="flex-1 py-3 rounded-xl text-sm" style={{ border: "1px solid rgba(218,165,32,0.2)", color: "rgba(255,255,255,0.6)" }}>Cancel</button>
              <button className="flex-1 py-3 rounded-xl text-sm font-medium" style={{ background: "linear-gradient(135deg, #DAA520, #B8860B)", color: "white" }}>Confirm Booking</button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
