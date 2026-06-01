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
  onSashaResponse?: (text: string) => void
  onListeningChange?: (listening: boolean) => void
  initialMessage?: string
}

const GOLF_KEYWORDS = ['golf', 'tee time', 'tee-time', 'fairway', 'caddy', 'green fee', 'driving range', 'montgomerie', 'hoiana', 'bluffs', 'vinpearl golf', 'ba na hills']

function isGolfMessage(text: string): boolean {
  const lower = text.toLowerCase()
  return GOLF_KEYWORDS.some(k => lower.includes(k))
}

function isGolfConversation(messages: any[]): boolean {
  return messages.some(m => isGolfMessage(m.content || ''))
}

export default function SashaChat({ user, itinerary, onItineraryUpdate, onSashaResponse, onListeningChange, initialMessage }: SashaChatProps) {
  const [messages, setMessages] = useState<any[]>(
    initialMessage ? [{ role: 'assistant', content: initialMessage }] : []
  )
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [golfHistory, setGolfHistory] = useState<any[]>([])
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendGolfMessage = async (content: string) => {
    setIsLoading(true)
    try {
      const apiUrl = 'https://sasha-travel-production.up.railway.app'
      const response = await axios.post(apiUrl + '/api/agents/golf', {
        message: content,
        conversation_history: golfHistory
      })
      const { response: golfResponse, messages: updatedHistory } = response.data
      setGolfHistory(updatedHistory)
      setMessages(prev => [...prev, { role: 'assistant', content: golfResponse, isGolf: true }])
      if (onSashaResponse) onSashaResponse(golfResponse)
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: "I had trouble reaching the golf booking system. Please try again." }])
    } finally {
      setIsLoading(false)
    }
  }

  const sendMessage = async (content: string) => {
    if (!content.trim()) return
    const userMessage = { role: 'user', content }
    const newMessages = [...messages, userMessage]
    setMessages(newMessages)
    setInput('')

    if (isGolfMessage(content) || isGolfConversation(messages)) {
      await sendGolfMessage(content)
      return
    }

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
          location: h.region?.name || 'Vietnam',
          price: h.rates?.[0]?.daily_prices?.[0] || 0,
          currency: 'USD', rationale: 'Matches your preferences'
        }))
      }
      setMessages(prev => [...prev, assistantMessage])
      if (onSashaResponse) onSashaResponse(sashaResponse)
      if (intent?.action === 'search_hotels' && api_data) {
        onItineraryUpdate({ ...itinerary, destination_summary: intent.params, depart_date: intent.params?.checkin, return_date: intent.params?.checkout })
      }
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: "I ran into a small issue. Could you try again?" }])
    } finally {
      setIsLoading(false)
    }
  }

  const golfMode = isGolfConversation(messages)

  return (
    <div className="flex flex-col h-full bg-[#0e0e16] rounded-3xl border border-white/5 overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5">
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
        <div className="ml-auto flex items-center gap-2">
          {golfMode && (
            <span className="text-xs bg-green-500/10 text-green-400 border border-green-500/20 px-3 py-1.5 rounded-full">⛳ Golf mode</span>
          )}
          <span className="text-xs bg-white/5 text-white/40 border border-white/10 px-3 py-1.5 rounded-full tracking-wide">Vietnam</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-8 h-8 rounded-2xl flex items-center justify-center flex-shrink-0 text-xs font-medium ${
              msg.role === 'assistant'
                ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white'
                : 'bg-white/10 text-white/60'
            }`}>
              {msg.role === 'assistant' ? 'S' : user.display_name[0]}
            </div>
            <div className="max-w-[90%]">
              <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === 'assistant'
                  ? 'bg-white/5 text-white/80 rounded-tl-sm border border-white/5'
                  : 'bg-gradient-to-br from-indigo-600 to-purple-600 text-white rounded-tr-sm'
              }`}>
                {msg.content}
              </div>
              {msg.isGolf && (
                <div className="mt-1 text-xs text-green-400/50 flex items-center gap-1">
                  <span>⛳</span><span>Golf concierge</span>
                </div>
              )}
              {msg.role === 'assistant' && msg.hotels && (
                <HotelResults hotels={msg.hotels} onSelect={(hotel) => setInput(`I'd like to go with ${hotel.name}`)} />
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs">S</div>
            <div className="px-4 py-3 rounded-2xl bg-white/5 border border-white/5">
              <Loader2 className="w-4 h-4 animate-spin text-white/40" />
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      <div className="px-3 pb-3 pt-2 border-t border-white/5">
        <div className="flex items-center gap-2 bg-white/5 rounded-2xl px-4 py-2 border border-white/5">
          <VoiceButton
            onTranscript={(text) => sendMessage(text)}
          />
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), sendMessage(input))}
            placeholder={golfMode ? "Ask about courses, tee times, bookings..." : "Ask Sasha anything about Vietnam..."}
            className="flex-1 bg-transparent text-sm text-white/80 placeholder-white/20 outline-none"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || isLoading}
            className="p-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 transition-colors"
          >
            <Send className="w-3.5 h-3.5 text-white" />
          </button>
        </div>
        <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {!golfMode ? (
            <>
              <button onClick={() => sendMessage("What are the best places to visit in Vietnam?")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">Best places →</button>
              <button onClick={() => sendMessage("I want to play golf in Danang")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">⛳ Golf →</button>
              <button onClick={() => sendMessage("Help me plan a 7 day Vietnam trip")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">Plan trip →</button>
            </>
          ) : (
            <>
              <button onClick={() => sendMessage("What's the best course in Danang?")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">Best course →</button>
              <button onClick={() => sendMessage("Show me courses under $100")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">Under $100 →</button>
              <button onClick={() => sendMessage("Tell me about The Bluffs Ho Tram")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">The Bluffs →</button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}