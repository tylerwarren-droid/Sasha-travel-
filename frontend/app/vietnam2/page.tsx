'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import dynamic from 'next/dynamic'
import SashaAvatar from '../components/SashaAvatar'
import SashaChat from './SashaChatLegacy'
import { stripMarkdown } from '@/lib/markdown'
import { User, Itinerary } from '@/types'

const MapPanel = dynamic(() => import('./MapPanel'), { ssr: false })

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

const VIETNAM_LOCATIONS = [
  { name: 'Hoi An Ancient Town', lat: 15.8801, lng: 108.3380, type: 'culture', description: 'UNESCO World Heritage Site' },
  { name: 'Ha Long Bay', lat: 20.9101, lng: 107.1839, type: 'nature', description: 'Iconic karst limestone seascape' },
  { name: 'Hanoi Old Quarter', lat: 21.0285, lng: 105.8542, type: 'city', description: 'Historic merchant streets' },
  { name: 'Ho Chi Minh City', lat: 10.8231, lng: 106.6297, type: 'city', description: 'Vibrant southern metropolis' },
  { name: 'Phu Quoc Island', lat: 10.2899, lng: 103.9840, type: 'beach', description: 'Pearl Island beaches' },
  { name: 'Sapa Rice Terraces', lat: 22.3364, lng: 103.8438, type: 'nature', description: 'Mountain highland trekking' },
  { name: 'Da Nang', lat: 16.0544, lng: 108.2022, type: 'city', description: 'Coastal gateway city' },
  { name: 'Hue Imperial City', lat: 16.4637, lng: 107.5909, type: 'culture', description: 'Ancient royal capital' },
]

const typeColors: Record<string, string> = {
  flight: '#3B82F6', hotel: '#10B981', restaurant: '#F59E0B',
  activity: '#8B5CF6', transfer: '#06B6D4', experience: '#EC4899', golf: '#84CC16',
}

interface Photo { url: string; thumb: string; description: string; photographer: string }

export default function Vietnam2Page() {
  const [itinerary, setItinerary] = useState<Itinerary>(INITIAL_ITINERARY)
  const speakFnRef = useRef<((text: string) => void) | null>(null)
  const interruptFnRef = useRef<(() => void) | null>(null)
  const gateRef = useRef<((value: boolean) => void) | null>(null)
  const lastRepeatTextRef = useRef<string>('')
  const isRespondingRef = useRef(false)
  const lockWatchdogRef = useRef<any>(null)
  const photoInterval = useRef<any>(null)
  const [isListening, setIsListening] = useState(false)
  const [chatMessages, setChatMessages] = useState<any[]>([])
  const [photos, setPhotos] = useState<Photo[]>([])
  const [activePhoto, setActivePhoto] = useState(0)
  const [engaged, setEngaged] = useState(false)
  const [activeTab, setActiveTab] = useState<'chat' | 'itinerary' | 'map'>('chat')
  const [started, setStarted] = useState(false)
  const [voiceReady, setVoiceReady] = useState(false)
  const [isAvatarSpeaking, setIsAvatarSpeaking] = useState(false)
  const [speakFn, setSpeakFn] = useState<((text: string) => void) | null>(null)

  const handleSetGate = useCallback((fn: (value: boolean) => void) => { gateRef.current = fn }, [])
  const handleGate = useCallback((value: boolean) => { gateRef.current?.(value) }, [])

  useEffect(() => {
    fetch('https://sasha-travel-production.up.railway.app/api/photos/search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'Vietnam landscape luxury travel', count: 5 })
    }).then(r => r.json()).then(data => { if (data.photos?.length > 0) { setPhotos(data.photos); setActivePhoto(0) } }).catch(() => {})
  }, [])

  useEffect(() => {
    if (photos.length <= 1) return
    clearInterval(photoInterval.current)
    photoInterval.current = setInterval(() => setActivePhoto(prev => (prev + 1) % photos.length), 6000)
    return () => clearInterval(photoInterval.current)
  }, [photos])

  const handleAvatarReady = useCallback((speak: (text: string) => void, interrupt: () => void) => {
    setSpeakFn(() => speak); speakFnRef.current = speak; interruptFnRef.current = interrupt
  }, [])

  const handleInterrupt = useCallback(() => { interruptFnRef.current?.() }, [])

  const handleEndSession = useCallback(() => {
    interruptFnRef.current?.()
    isRespondingRef.current = false
    clearTimeout(lockWatchdogRef.current)
    setIsAvatarSpeaking(false)
    speakFnRef.current = null; interruptFnRef.current = null
    setEngaged(false); setStarted(false)
  }, [])

  const handlePhotos = useCallback((newPhotos: any[]) => {
    if (newPhotos?.length > 0) { setPhotos(newPhotos); setActivePhoto(0) }
  }, [])

  const handleSashaFinished = useCallback(() => {
    isRespondingRef.current = false; clearTimeout(lockWatchdogRef.current)
  }, [])

  const handleSashaResponse = useCallback((text: string) => {
    if (!text || !speakFnRef.current) return
    const spoken = stripMarkdown(text)
    lastRepeatTextRef.current = spoken
    isRespondingRef.current = true
    speakFnRef.current(spoken)
    setEngaged(true)
    clearTimeout(lockWatchdogRef.current)
    const ms = Math.min(35000, Math.max(10000, text.length * 90)) + 4000
    lockWatchdogRef.current = setTimeout(() => {
      if (isRespondingRef.current) { isRespondingRef.current = false; setIsAvatarSpeaking(false); gateRef.current?.(false) }
    }, ms)
    if (/day\s+\d+/i.test(text)) setActiveTab('itinerary')
  }, [])

  const handleItineraryUpdate = useCallback((newItinerary: Itinerary) => {
    setItinerary(newItinerary)
    if (newItinerary.items?.length > 0) setActiveTab('itinerary')
  }, [])

  return (
    <main className="h-screen flex flex-col overflow-hidden" style={{ background: '#06060F', fontFamily: "'Inter', system-ui, sans-serif" }}>

      <header className="flex items-center justify-between px-6 py-3 flex-shrink-0" style={{ background: 'rgba(6,6,15,0.95)', borderBottom: '1px solid rgba(218,165,32,0.15)', backdropFilter: 'blur(20px)' }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold" style={{ background: 'linear-gradient(135deg, #DAA520, #B8860B)', color: '#fff' }}>VN</div>
          <div>
            <div className="text-sm font-bold" style={{ color: '#F5F0E8' }}>Discover Vietnam</div>
            <div className="text-xs" style={{ color: 'rgba(218,165,32,0.6)' }}>AI Travel Concierge · Ministry of Tourism Partner</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {started && (
            <button onClick={handleEndSession} className="text-xs px-3 py-1.5 rounded-full border" style={{ color: '#f87171', borderColor: 'rgba(248,113,113,0.3)', background: 'rgba(248,113,113,0.08)' }}>
              ■ End Session
            </button>
          )}
          <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: '#10B981' }} />
          <span className="text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>Sasha Online</span>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden" style={{ minHeight: 0 }}>

        {/* LEFT — Avatar + Photos */}
        <div className="flex flex-col flex-shrink-0" style={{ width: '300px', borderRight: '1px solid rgba(218,165,32,0.1)' }}>
          <div className="relative flex-shrink-0 overflow-hidden transition-all duration-700" style={{ height: engaged ? '170px' : '250px', background: '#0a0a18' }}>
            {started ? (
              <SashaAvatar
                onAvatarReady={handleAvatarReady}
                isListening={isListening}
                onGate={handleGate}
                onAvatarSpeakingChange={setIsAvatarSpeaking}
                onReadyToListen={() => setVoiceReady(true)}
                onSashaFinished={handleSashaFinished}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #0a0a18, #1a1a30)' }}>
                <div className="text-center"><div className="text-4xl mb-2">🇻🇳</div><div className="text-xs" style={{ color: 'rgba(218,165,32,0.5)' }}>Tap to meet Sasha</div></div>
              </div>
            )}
            {isAvatarSpeaking && (
              <div className="absolute bottom-3 left-0 right-0 flex justify-center gap-1">
                {[0,1,2,3,4].map(i => (
                  <div key={i} className="w-1 rounded-full" style={{ height: '12px', background: '#DAA520', animation: `soundwave 0.8s ease-in-out ${i*0.1}s infinite alternate` }} />
                ))}
              </div>
            )}
          </div>

          <div className="flex-1 overflow-hidden relative" style={{ minHeight: 0 }}>
            {photos.length > 0 ? (
              <div className="relative w-full h-full">
                <img key={activePhoto} src={photos[activePhoto]?.url} alt={photos[activePhoto]?.description} className="w-full h-full object-cover" style={{ opacity: 0.85, animation: 'fadeIn 0.6s ease' }} />
                <div className="absolute inset-0" style={{ background: 'linear-gradient(to bottom, transparent 40%, rgba(6,6,15,0.95) 100%)' }} />
                <div className="absolute bottom-0 left-0 right-0 p-4">
                  <div className="text-xs font-medium mb-1 truncate" style={{ color: '#F5F0E8' }}>{photos[activePhoto]?.description}</div>
                  <div className="text-xs" style={{ color: 'rgba(218,165,32,0.6)' }}>📷 {photos[activePhoto]?.photographer}</div>
                  <div className="flex gap-1.5 mt-3">
                    {photos.map((_, i) => (
                      <button key={i} onClick={() => setActivePhoto(i)} className="rounded-full transition-all" style={{ width: i === activePhoto ? '20px' : '6px', height: '6px', background: i === activePhoto ? '#DAA520' : 'rgba(255,255,255,0.25)' }} />
                    ))}
                  </div>
                </div>
                <div className="absolute top-3 right-3 flex flex-col gap-1.5">
                  {photos.slice(0,4).map((p, i) => (
                    <button key={i} onClick={() => setActivePhoto(i)} className="rounded-lg overflow-hidden transition-all" style={{ width: '40px', height: '30px', border: `2px solid ${i === activePhoto ? '#DAA520' : 'rgba(255,255,255,0.15)'}` }}>
                      <img src={p.thumb} alt="" className="w-full h-full object-cover" />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="w-full h-full flex items-center justify-center" style={{ background: '#0a0a18' }}>
                <div className="text-white/10 text-sm">Loading photos...</div>
              </div>
            )}
          </div>
        </div>

        {/* CENTER — Tabs */}
        <div className="flex-1 flex flex-col overflow-hidden" style={{ minWidth: 0 }}>
          <div className="flex flex-shrink-0" style={{ borderBottom: '1px solid rgba(218,165,32,0.1)', background: 'rgba(6,6,15,0.8)' }}>
            {[
              { key: 'chat', label: 'Sasha', icon: '✦' },
              { key: 'itinerary', label: 'Itinerary', icon: '📋', badge: itinerary.items?.length || 0 },
              { key: 'map', label: 'Map', icon: '🗺' },
            ].map(tab => (
              <button key={tab.key} onClick={() => setActiveTab(tab.key as any)}
                className="flex items-center gap-2 px-5 py-3 text-xs font-medium transition-all"
                style={{ color: activeTab === tab.key ? '#DAA520' : 'rgba(255,255,255,0.3)', borderBottom: activeTab === tab.key ? '2px solid #DAA520' : '2px solid transparent' }}
              >
                <span>{tab.icon}</span>{tab.label}
                {(tab.badge ?? 0) > 0 && <span className="px-1.5 py-0.5 rounded-full font-bold" style={{ background: '#DAA520', color: '#06060F', fontSize: '9px' }}>{tab.badge}</span>}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-hidden" style={{ minHeight: 0 }}>
            {activeTab === 'chat' && started && (
              <SashaChat
                user={DEMO_USER} itinerary={itinerary}
                onItineraryUpdate={handleItineraryUpdate}
                onSashaResponse={handleSashaResponse}
                onListeningChange={setIsListening}
                onSetGate={handleSetGate} onInterrupt={handleInterrupt}
                onPhotos={handlePhotos}
                presetPrompts={['Tell me about Hoi An', 'Best golf courses', 'Plan a 7 day trip', 'Phu Quoc beaches']}
                messages={chatMessages} setMessages={setChatMessages}
                avatarSpeaking={isAvatarSpeaking}
                avatarSpeechGetter={() => lastRepeatTextRef.current}
                isRespondingRef={isRespondingRef} readyToListen={voiceReady}
              />
            )}
            {activeTab === 'chat' && !started && (
              <div className="h-full flex items-center justify-center">
                <div className="text-center"><div className="text-4xl mb-4">🇻🇳</div><div className="text-sm" style={{ color: 'rgba(255,255,255,0.3)' }}>Tap below to start</div></div>
              </div>
            )}

            {activeTab === 'itinerary' && (
              <div className="h-full overflow-y-auto p-4 space-y-3" style={{ background: '#07070F' }}>
                <div className="rounded-2xl p-5" style={{ background: 'linear-gradient(135deg, #111128, #0d0d20)', border: '1px solid rgba(218,165,32,0.2)' }}>
                  <div className="text-xs font-medium mb-1" style={{ color: 'rgba(218,165,32,0.7)' }}>CURATED FOR ALEX & MAYA</div>
                  <div className="text-xl font-bold" style={{ color: '#F5F0E8' }}>{itinerary.title}</div>
                  {itinerary.total_fiat > 0 && <div className="text-sm mt-2" style={{ color: '#DAA520' }}>${itinerary.total_fiat.toLocaleString()} total</div>}
                </div>
                {itinerary.items?.length > 0 ? itinerary.items.map((item: any, i: number) => (
                  <div key={i} className="rounded-xl p-4" style={{ background: '#0d0d1e', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div className="flex items-start gap-3">
                      <div className="px-2 py-0.5 rounded text-xs font-bold uppercase flex-shrink-0" style={{ background: `${typeColors[item.type] || '#6B7280'}22`, color: typeColors[item.type] || '#6B7280', border: `1px solid ${typeColors[item.type] || '#6B7280'}44` }}>{item.type}</div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium" style={{ color: '#F5F0E8' }}>{item.display_name}</div>
                        {item.sasha_rationale && <div className="text-xs mt-1 italic" style={{ color: 'rgba(218,165,32,0.6)' }}>{item.sasha_rationale}</div>}
                      </div>
                      {item.price_fiat > 0 && <div className="text-sm font-semibold flex-shrink-0" style={{ color: '#DAA520' }}>${item.price_fiat.toLocaleString()}</div>}
                    </div>
                  </div>
                )) : (
                  <div className="flex flex-col items-center justify-center py-16">
                    <div className="text-5xl mb-4">✈️</div>
                    <div className="text-sm" style={{ color: 'rgba(255,255,255,0.3)' }}>Ask Sasha to plan your trip</div>
                    <div className="text-xs mt-1" style={{ color: 'rgba(218,165,32,0.4)' }}>Your itinerary builds here as you chat</div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'map' && <MapPanel locations={VIETNAM_LOCATIONS} />}
          </div>
        </div>
      </div>

      {!started && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center cursor-pointer" style={{ background: 'rgba(6,6,15,0.97)', backdropFilter: 'blur(20px)' }} onClick={() => setStarted(true)}>
          {photos.length > 0 && <div className="absolute inset-0 overflow-hidden"><img src={photos[0]?.url} alt="" className="w-full h-full object-cover" style={{ opacity: 0.08 }} /></div>}
          <div className="relative text-center">
            <div className="text-6xl mb-6">🇻🇳</div>
            <div className="text-3xl font-bold mb-2" style={{ color: '#DAA520', letterSpacing: '-0.5px' }}>Discover Vietnam</div>
            <div className="text-sm mb-8" style={{ color: 'rgba(255,255,255,0.3)', letterSpacing: '0.2em', textTransform: 'uppercase' }}>AI Travel Concierge</div>
            <div className="inline-flex items-center gap-3 px-8 py-4 rounded-2xl text-base font-bold" style={{ background: 'linear-gradient(135deg, #DAA520, #B8860B)', color: '#fff', boxShadow: '0 8px 32px rgba(218,165,32,0.4)', animation: 'pulse 2s ease-in-out infinite' }}>
              <span>▶</span> Tap to start
            </div>
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
        @keyframes pulse { 0%,100% { box-shadow: 0 8px 32px rgba(218,165,32,0.4); } 50% { box-shadow: 0 8px 48px rgba(218,165,32,0.7); } }
        @keyframes soundwave { from { height: 4px; opacity: 0.5; } to { height: 16px; opacity: 1; } }
      `}</style>
    </main>
  )
}
