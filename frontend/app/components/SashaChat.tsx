'use client'
import { useState, useRef, useEffect } from 'react'
import { Send, Loader2 } from 'lucide-react'
import { User, Itinerary } from '@/types'
import VoiceButton from './VoiceButton'
import HotelResults from './HotelResults'
import axios from 'axios'

interface SashaChatProps {
  user: User
  itinerary: Itinerary
  onItineraryUpdate: (itinerary: Itinerary) => void
}

export default function SashaChat({ user, itinerary, onItineraryUpdate }: SashaChatProps) {
  const [messages, setMessages] = useState<any[]>([{
    role: 'assistant',
    content: `Welcome back, ${user.display_name}! ${user.past_trips && user.past_trips.length > 0 ? `How was your ${user.past_trips[0].title}? ` : ''}Ready to plan your next escape? 🌴`
  }])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

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
      const response = await axios.post(process.env.NEXT_PUBLIC_API_URL + '/conversation/chat', {
        messages: newMessages, user, itinerary
      })
      const { response: sashaResponse, intent, api_data } = response.data
      const assistantMessage: any = { role: 'assistant', content: sashaResponse }
      if (api_data?.data?.hotels) {
        assistantMessage.hotels = api_data.data.hotels.slice(0, 3).map((h: any) => ({
          id: h.id, name: h.name, stars: h.star_rating || 5,
          location: h.region?.name || 'Maldives',
          price: h.rates?.[0]?.daily_prices?.[0] || 0,
          currency: 'GBP', rationale: 'Matches your preferences'
        }))
      }
      setMessages(prev => [...prev, assistantMessage])
      if (intent?.action === 'search_hotels' && api_data) {
        onItineraryUpdate({ ...itinerary, destination_summary: intent.params, depart_date: intent.params?.checkin, return_date: intent.params?.checkout })
      }
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: "I ran into a small issue. Could you try again?" }])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-[#0e0e16] rounded-3xl border border-white/5 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-4 px-6 py-4 border-b border-white/5">
        <div className="relative">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-900/40">
            <span className="text-white font-semibold text-sm">S</span>
          </div>
          <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-emerald-400 border-2 border-[#0e0e16]" />
        </div>
        <div>
          <div className="text-sm font-medium text-white">Sasha</div>
          <div className="text-xs text-emerald-400/70">Online</div>
        </div>
        <div className="ml-auto">
          <span className="text-xs bg-white/5 text-white/40 border border-white/10 px-3 py-1.5 rounded-full tracking-wide">
            Beach escapes
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-8 h-8 rounded-2xl flex items-center justify-center flex-shrink-0 text-xs font-medium ${
              msg.role === 'assistant'
                ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg shadow-indigo-900/30'
                : 'bg-white/10 text-white/60'
            }`}>
              {msg.role === 'assistant' ? 'S' : user.display_name[0]}
            </div>
            <div className="max-w-[80%]">
              <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                msg.role === 'assistant'
                  ? 'bg-white/5 text-white/80 rounded-tl-sm border border-white/5'
                  : 'bg-gradient-to-br from-indigo-600 to-purple-600 text-white rounded-tr-sm shadow-lg shadow-indigo-900/30'
              }`}>
                {msg.content}
              </div>
              {msg.role === 'assistant' && msg.hotels && (
                <HotelResults hotels={msg.hotels} onSelect={(hotel) => setInput(`I'd like to go with ${hotel.name}`)} />
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0">
              <span className="text-white text-xs font-medium">S</span>
            </div>
            <div className="bg-white/5 border border-white/5 px-4 py-3 rounded-2xl rounded-tl-sm">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-4 border-t border-white/5 flex items-center gap-3">
        <VoiceButton onTranscript={(t) => sendMessage(t)} disabled={isLoading} />
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendMessage(input)}
          placeholder="Say it or type here..."
          className="flex-1 h-11 px-5 bg-white/5 border border-white/10 rounded-full text-sm text-white placeholder-white/20 outline-none focus:border-indigo-500/40 transition-colors"
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || isLoading}
          className="w-11 h-11 rounded-full bg-gradient-to-br from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 flex items-center justify-center flex-shrink-0 disabled:opacity-30 transition-all shadow-lg shadow-indigo-900/30"
        >
          <Send className="w-4 h-4 text-white" />
        </button>
      </div>
    </div>
  )
}
