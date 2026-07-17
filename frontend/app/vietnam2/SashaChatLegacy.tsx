'use client'
import { useState, useRef, useEffect, MutableRefObject } from 'react'
import { Send, Loader2 } from 'lucide-react'
import { User, Itinerary } from '@/types'
import VoiceButton from './VoiceButton'
import { renderMarkdown } from '@/lib/markdown'
import axios from 'axios'

interface SashaChatProps {
  user: User
  itinerary: Itinerary
  onItineraryUpdate: (itinerary: Itinerary) => void
  onSashaResponse?: (text: string) => void
  onListeningChange?: (listening: boolean) => void
  onPhotos?: (photos: any[]) => void
  emptyState?: React.ReactNode
  initialMessage?: string
  avatarSpeaking?: boolean
  onInterrupt?: () => void
  presetPrompts?: string[]
  onSetGate?: (gate: (value: boolean) => void) => void
  avatarSpeechGetter?: () => string
  isRespondingRef?: MutableRefObject<boolean>
  readyToListen?: boolean
  // Lifted state — pass from parent to preserve history across remounts
  messages?: any[]
  setMessages?: React.Dispatch<React.SetStateAction<any[]>>
}

const API_URL = process.env.NEXT_PUBLIC_API_URL

export default function SashaChat({ user, itinerary, onItineraryUpdate, onSashaResponse, onListeningChange, onPhotos, initialMessage, emptyState, avatarSpeaking, onInterrupt, presetPrompts, onSetGate, avatarSpeechGetter, isRespondingRef, readyToListen, messages: propMessages, setMessages: propSetMessages }: SashaChatProps) {
  const [localMessages, setLocalMessages] = useState<any[]>(
    initialMessage ? [{ role: 'assistant', content: initialMessage }] : []
  )
  // Use lifted state when provided (persists across tab remounts), else fall back to local state
  const messages = propMessages !== undefined ? propMessages : localMessages
  const setMessages = propSetMessages ?? setLocalMessages

  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)
  // Single-flight guard: one conductor request at a time. Prevents duplicate STT
  // finals (or fast double-taps) from firing concurrent calls and stacking replies.
  const inFlightRef = useRef(false)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (content: string) => {
    if (!content.trim()) return
    if (isRespondingRef?.current) {
      console.log('[LOCK] ignoring transcript — Sasha is responding')
      return
    }
    if (inFlightRef.current) {
      console.log('[Conductor] ignoring — a request is already in flight')
      return
    }
    inFlightRef.current = true
    console.log('[Conductor] API_URL:', API_URL)
    const historyBeforeMessage = messages  // snapshot before appending
    setMessages(prev => [...prev, { role: 'user', content }])
    setInput('')
    setIsLoading(true)
    try {
      const response = await axios.post(API_URL + '/api/agents/conductor', {
        message: content,
        conversation_history: historyBeforeMessage
      }, { timeout: 30000 })  // bound the call so a hung backend can't stall the turn
      const { response: sashaResponse, conversation_history, photos } = response.data
      // Replace local messages with server-authoritative history
      if (conversation_history?.length > 0) {
        setMessages(conversation_history)
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: sashaResponse }])
      }
      if (onSashaResponse) onSashaResponse(sashaResponse)
      if (photos?.length > 0) onPhotos?.(photos)
    } catch (error: any) {
      console.error('[Conductor] error:', error?.response?.status, error?.response?.data, error?.message)
      // Speak a graceful fallback so the avatar is never silent on a backend hiccup —
      // this is what "the avatar doesn't respond" looked like to the user.
      const fallback = "Sorry, I didn't quite catch that — could you say it again?"
      setMessages(prev => [...prev, { role: 'assistant', content: fallback }])
      onSashaResponse?.(fallback)
    } finally {
      setIsLoading(false)
      inFlightRef.current = false
    }
  }

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
        <div className="ml-auto">
          <span className="text-xs bg-white/5 text-white/40 border border-white/10 px-3 py-1.5 rounded-full tracking-wide">Vietnam</span>
        </div>
      </div>

      {presetPrompts && presetPrompts.length > 0 && (
        <div className="flex gap-1.5 px-3 pt-2.5 pb-1 flex-wrap flex-shrink-0">
          {presetPrompts.map(prompt => (
            <button
              key={prompt}
              onClick={() => sendMessage(prompt)}
              className="text-xs rounded-full px-3 py-1 transition-opacity hover:opacity-75"
              style={{ background: 'rgba(218,165,32,0.1)', border: '1px solid rgba(218,165,32,0.3)', color: '#DAA520' }}
            >
              {prompt}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
        {messages.length === 0 && emptyState}
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
              <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                msg.role === 'assistant'
                  ? 'bg-white/5 text-white/80 rounded-tl-sm border border-white/5'
                  : 'bg-gradient-to-br from-indigo-600 to-purple-600 text-white rounded-tr-sm whitespace-pre-wrap'
              }`}>
                {msg.role === 'assistant' ? renderMarkdown(msg.content) : msg.content}
              </div>
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
            autoStart={true}
            readyToListen={readyToListen}
            avatarSpeaking={avatarSpeaking}
            onInterrupt={onInterrupt}
            onSetGate={onSetGate}
            avatarSpeechGetter={avatarSpeechGetter}
          />
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), sendMessage(input))}
            placeholder="Ask Sasha anything..."
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
          <button onClick={() => sendMessage("What are the best places to visit in Vietnam?")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">Best places →</button>
          <button onClick={() => sendMessage("I want to play golf in Danang")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">⛳ Golf →</button>
          <button onClick={() => sendMessage("Help me plan a 7 day Vietnam trip")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">Plan trip →</button>
          <button onClick={() => sendMessage("Find me flights to Hanoi")} className="text-xs text-white/30 hover:text-white/60 transition-colors whitespace-nowrap flex-shrink-0">Flights →</button>
        </div>
      </div>
    </div>
  )
}
