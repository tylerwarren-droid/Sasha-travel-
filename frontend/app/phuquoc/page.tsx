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
  sasha_context: 'Alex is interested in Phu Quoc as an emerging luxury destination ahead of APEC 2027. Interested in beach resorts, golf, and getting ahead of the crowd before prices spike.',
  travellers: [
    { relation: 'self', first_name: 'Alex' },
    { relation: 'partner', first_name: 'Maya' },
  ],
  preferences: [
    { key: 'accommodation.type', value: 'luxury_beach_resort', source: 'explicit', confidence: 1.0, is_active: true },
    { key: 'experience.type', value: 'beach_and_wellness', source: 'explicit', confidence: 1.0, is_active: true },
  ],
  past_trips: [
    { title: 'Vietnam — Hanoi and Ha Long Bay', return_date: 'Summer 2024' },
    { title: 'Bali — Seminyak and Ubud', return_date: 'Winter 2023' },
  ],
  ota_affinity: ['beach', 'luxury']
}

const INITIAL_ITINERARY: Itinerary = {
  title: 'Phu Quoc Discovery',
  ota_channel: 'beach',
  status: 'draft',
  total_fiat: 0,
  items: []
}

const APEC_WELCOME = `Hi Alex! 🌴 Welcome to Phu Quoc — Vietnam's pearl island and the host of APEC 2027.

Right now is the smartest time to visit. Vietnam's first LRT, a brand new international airport terminal, and Sun Group's luxury hotel city are all under construction. Prices are still pre-APEC. By 2027 this island will be on every luxury traveller's radar.

Shall I show you the best resorts, beaches, and experiences — before the world catches on?`

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
    // Proactive APEC briefing on load
    setTimeout(() => speak(APEC_WELCOME), 2000)
  }, [])

  const handleSashaResponse = useCallback((text: string) => {
    if (speakFn) speakFn(text)
    const lower = text.toLowerCase()
    const spots = ['vinpearl', 'grand world', 'sun world', 'long beach', 'sao beach', 'phu quoc', 'duong dong', 'bai dai']
    for (const spot of spots) {
      if (lower.includes(spot)) { setPhotoQuery(`${spot} Phu Quoc Vietnam`); return }
    }
  }, [speakFn])

  const handleItineraryUpdate = useCallback((newItinerary: Itinerary) => {
    setItinerary(newItinerary)
    if (newItinerary.items?.length > 0) setRightTab('itinerary')
  }, [])

  return (
    <main className="h-screen flex flex-col overflow-hidden" style={{ background: '#080810' }}>

      {/* HEADER */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/5 flex-shrink-0" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(10px)' }}>
        <div className="flex items-center gap-2">
          <span className="text-lg">🏝️</span>
          <span className="font-bold tracking-wide text-sm" style={{ color: '#00B4D8' }}>Discover Phu Quoc</span>
          <div className="w-px h-3 bg-white/10" />
          <span className="text-xs text-white/30 tracking-widest uppercase hidden sm:block">AI Travel Concierge</span>
        </div>
        <div className="text-xs px-2 py-1 rounded-full border flex items-center gap-1" style={{ color: '#00B4D8', borderColor: 'rgba(0,180,216,0.3)', background: 'rgba(0,180,216,0.1)' }}>
          🌏 APEC 2027 Host
        </div>
      </div>

      {/* MIDDLE — Avatar + Chat/Itinerary */}
      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>

        {/* LEFT — Avatar */}
        <div className="flex-shrink-0 overflow-hidden border-r border-white/5" style={{ width: '38%' }}>
          <SashaAvatar onAvatarReady={handleAvatarReady} isListening={isListening} />
        </div>

        {/* RIGHT — Chat OR Itinerary */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* Tabs */}
          <div className="flex border-b border-white/5 flex-shrink-0">
            <button
              onClick={() => setRightTab('chat')}
              className="flex-1 py-2.5 text-xs font-medium transition-all"
              style={{
                color: rightTab === 'chat' ? '#00B4D8' : 'rgba(255,255,255,0.3)',
                borderBottom: rightTab === 'chat' ? '2px solid #00B4D8' : '2px solid transparent'
              }}
            >
              💬 Sasha
            </button>
            <button
              onClick={() => setRightTab('itinerary')}
              className="flex-1 py-2.5 text-xs font-medium transition-all relative"
              style={{
                color: rightTab === 'itinerary' ? '#00B4D8' : 'rgba(255,255,255,0.3)',
                borderBottom: rightTab === 'itinerary' ? '2px solid #00B4D8' : '2px solid transparent'
              }}
            >
              🗺️ Itinerary
              {itinerary.items?.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full" style={{ background: '#00B4D8', color: '#000', fontSize: '9px' }}>
                  {itinerary.items.length}
                </span>
              )}
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-hidden">
            {rightTab === 'chat' ? (
              <PhuQuocChat
                user={DEMO_USER}
                itinerary={itinerary}
                onItineraryUpdate={handleItineraryUpdate}
                onSashaResponse={handleSashaResponse}
                onListeningChange={setIsListening}
              />
            ) : (
              <div className="flex flex-col h-full">
                <div className="flex-1 overflow-y-auto">
                  <ItineraryPanel
                    itinerary={itinerary}
                    user={DEMO_USER}
                    onPay={(method) => setPaymentModal(method)}
                  />
                </div>
                <div className="flex-shrink-0">
                  <PhuQuocChat
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
                className="relative rounded-xl overflow-hidden transition-all duration-300"
                style={{
                  border: i === activePhoto ? '2px solid #00B4D8' : '2px solid transparent',
                  flex: i === activePhoto ? '2' : '1'
                }}
              >
                <img src={photo.thumb} alt={photo.description} className="w-full h-full object-cover" style={{ opacity: i === activePhoto ? 1 : 0.5 }} />
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
            <div className="text-white/20 text-xs">Loading Phu Quoc photos...</div>
          </div>
        )}
      </div>

      {paymentModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="rounded-2xl p-6 w-80 shadow-xl" style={{ background: '#1a1a2e', border: '1px solid rgba(0,180,216,0.3)' }}>
            <div className="text-lg font-semibold mb-1" style={{ color: '#00B4D8' }}>Complete Booking</div>
            <div className="text-sm mb-6" style={{ color: 'rgba(255,255,255,0.4)' }}>Total: ${itinerary.total_fiat.toLocaleString()}</div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setPaymentModal(null)} className="flex-1 py-3 rounded-xl text-sm" style={{ border: '1px solid rgba(0,180,216,0.2)', color: 'rgba(255,255,255,0.6)' }}>Cancel</button>
              <button className="flex-1 py-3 rounded-xl text-sm font-medium" style={{ background: 'linear-gradient(135deg, #00B4D8, #0077B6)', color: 'white' }}>Confirm</button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}

// Phu Quoc specific chat — same as SashaChat but scoped context
function PhuQuocChat({ user, itinerary, onItineraryUpdate, onSashaResponse, onListeningChange, inputOnly }: any) {
  const [messages, setMessages] = useState<any[]>([{
    role: 'assistant',
    content: APEC_WELCOME
  }])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const { Send, Loader2 } = require('lucide-react')
  const axios = require('axios').default

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (content: string) => {
    if (!content.trim()) return
    const userMessage = { role: 'user', content }
    const newMessages = [...messages, userMessage]
    setMessages(newMessages)
    setInput('')
    setIsLoading(true)
    try {
      const response = await axios.post('https://sasha-travel-production.up.railway.app/api/agents/conductor', {
        message: content,
        conversation_history: messages.map(m => ({ role: m.role, content: m.content }))
      })
      const sashaResponse = response.data.response
      setMessages(prev => [...prev, { role: 'assistant', content: sashaResponse }])
      if (onSashaResponse) onSashaResponse(sashaResponse)
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: "I ran into a small issue. Could you try again?" }])
    } finally {
      setIsLoading(false)
    }
  }

  const inputBar = (
    <div className="px-3 pb-3 pt-2 border-t border-white/5">
      <div className="flex items-center gap-2 bg-white/5 rounded-2xl px-3 py-2 border border-white/5">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), sendMessage(input))}
          placeholder="Ask about Phu Quoc..."
          className="flex-1 bg-transparent text-sm text-white/80 placeholder-white/20 outline-none"
        />
        <button onClick={() => sendMessage(input)} disabled={!input.trim() || isLoading}
          className="p-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-30 transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
        </button>
      </div>
      <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1">
        <button onClick={() => sendMessage("What are the best beaches in Phu Quoc?")} className="text-xs text-white/30 hover:text-white/60 whitespace-nowrap flex-shrink-0">Best beaches →</button>
        <button onClick={() => sendMessage("Tell me about APEC 2027 and what it means for Phu Quoc")} className="text-xs text-white/30 hover:text-white/60 whitespace-nowrap flex-shrink-0">🌏 APEC 2027 →</button>
        <button onClick={() => sendMessage("What luxury resorts are in Phu Quoc?")} className="text-xs text-white/30 hover:text-white/60 whitespace-nowrap flex-shrink-0">Luxury resorts →</button>
        <button onClick={() => sendMessage("Golf in Phu Quoc?")} className="text-xs text-white/30 hover:text-white/60 whitespace-nowrap flex-shrink-0">⛳ Golf →</button>
      </div>
    </div>
  )

  if (inputOnly) return inputBar

  return (
    <div className="flex flex-col h-full bg-[#0e0e16] overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5 flex-shrink-0">
        <div className="relative">
          <div className="w-8 h-8 rounded-2xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #00B4D8, #0077B6)' }}>
            <span className="text-white font-semibold text-xs">S</span>
          </div>
          <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-[#0e0e16]" />
        </div>
        <div>
          <div className="text-sm font-medium text-white">Sasha</div>
          <div className="text-xs text-emerald-400/70">Online</div>
        </div>
        <div className="ml-auto">
          <span className="text-xs px-2 py-1 rounded-full border" style={{ color: '#00B4D8', borderColor: 'rgba(0,180,216,0.2)', background: 'rgba(0,180,216,0.05)' }}>Phu Quoc</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-2 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 text-xs font-medium ${msg.role === 'assistant' ? 'text-white' : 'bg-white/10 text-white/60'}`}
              style={msg.role === 'assistant' ? { background: 'linear-gradient(135deg, #00B4D8, #0077B6)' } : {}}>
              {msg.role === 'assistant' ? 'S' : user.display_name[0]}
            </div>
            <div className="max-w-[90%]">
              <div className={`px-3 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${msg.role === 'assistant' ? 'bg-white/5 text-white/80 rounded-tl-sm border border-white/5' : 'text-white rounded-tr-sm'}`}
                style={msg.role === 'user' ? { background: 'linear-gradient(135deg, #00B4D8, #0077B6)' } : {}}>
                {msg.content}
              </div>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-2">
            <div className="w-7 h-7 rounded-xl flex items-center justify-center text-white text-xs" style={{ background: 'linear-gradient(135deg, #00B4D8, #0077B6)' }}>S</div>
            <div className="px-3 py-2.5 rounded-2xl bg-white/5 border border-white/5">
              <div className="w-4 h-4 border-2 border-cyan-400/40 border-t-cyan-400 rounded-full animate-spin" />
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {inputBar}
    </div>
  )
}
