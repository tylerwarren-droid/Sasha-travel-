'use client'
import { useState, useRef, useEffect } from 'react'
import { Send, Loader2 } from 'lucide-react'
import { Message, User, Itinerary } from '@/types'
import VoiceButton from './VoiceButton'
import HotelResults from './HotelResults'
import axios from 'axios'
interface SashaChatProps {
  user: User
  itinerary: Itinerary
  onItineraryUpdate: (itinerary: Itinerary) => void
}
export default function SashaChat({ user, itinerary, onItineraryUpdate }: SashaChatProps) {
  const [messages, setMessages] = useState<any[]>([{role:'assistant',content:`Welcome back, ${user.display_name}! ${user.past_trips&&user.past_trips.length>0?`How was your ${user.past_trips[0].title}? `:''}Ready to plan your next escape? 🌴`}])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)
  useEffect(()=>{chatEndRef.current?.scrollIntoView({behavior:'smooth'})},[messages])
  const sendMessage = async (content: string) => {
    if (!content.trim()) return
    const userMessage = { role: 'user', content }
    const newMessages = [...messages, userMessage]
    setMessages(newMessages)
    setInput('')
    setIsLoading(true)
    try {
      const response = await axios.post(process.env.NEXT_PUBLIC_API_URL + '/conversation/chat',{messages:newMessages,user,itinerary})
      const { response: sashaResponse, intent, api_data } = response.data
      const assistantMessage: any = { role: 'assistant', content: sashaResponse }
      if (api_data?.data?.hotels) {
        assistantMessage.hotels = api_data.data.hotels.slice(0,3).map((h:any)=>({id:h.id,name:h.name,stars:h.star_rating||5,location:h.region?.name||'Maldives',price:h.rates?.[0]?.daily_prices?.[0]||0,currency:'GBP',rationale:'Matches your preferences'}))
      }
      setMessages(prev=>[...prev,assistantMessage])
      if (intent?.action==='search_hotels'&&api_data) {
        onItineraryUpdate({...itinerary,destination_summary:intent.params,depart_date:intent.params?.checkin,return_date:intent.params?.checkout})
      }
    } catch(error) {
      setMessages(prev=>[...prev,{role:'assistant',content:"I ran into a small issue. Could you try again?"}])
    } finally {
      setIsLoading(false)
    }
  }
  return (
    <div className="flex flex-col h-full bg-white rounded-2xl shadow-sm border border-gray-100">
      <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-100">
        <div className="w-9 h-9 rounded-full bg-indigo-600 flex items-center justify-center"><span className="text-white text-sm font-medium">S</span></div>
        <div><div className="font-semibold text-gray-900 text-sm">Sasha</div><div className="text-xs text-green-500 flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-green-500"></div>Online</div></div>
        <div className="ml-auto"><span className="text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-3 py-1 rounded-full">Beach escapes</span></div>
      </div>
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {messages.map((msg,i)=>(
          <div key={i} className={`flex gap-3 ${msg.role==='user'?'flex-row-reverse':''}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${msg.role==='assistant'?'bg-indigo-600':'bg-gray-200'}`}>
              <span className={`text-xs font-medium ${msg.role==='assistant'?'text-white':'text-gray-600'}`}>{msg.role==='assistant'?'S':user.display_name[0]}</span>
            </div>
            <div className="max-w-[85%]">
              <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${msg.role==='assistant'?'bg-gray-50 text-gray-800 rounded-tl-sm':'bg-indigo-600 text-white rounded-tr-sm'}`}>{msg.content}</div>
              {msg.role==='assistant'&&msg.hotels&&(<HotelResults hotels={msg.hotels} onSelect={(hotel)=>{setInput(`I'd like to go with ${hotel.name}`)}}/>)}
            </div>
          </div>
        ))}
        {isLoading&&(<div className="flex gap-3"><div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center flex-shrink-0"><span className="text-white text-xs font-medium">S</span></div><div className="bg-gray-50 px-4 py-3 rounded-2xl rounded-tl-sm"><Loader2 className="w-4 h-4 animate-spin text-indigo-600"/></div></div>)}
        <div ref={chatEndRef}/>
      </div>
      <div className="px-4 py-3 border-t border-gray-100 flex items-center gap-3">
        <VoiceButton onTranscript={(t)=>sendMessage(t)} disabled={isLoading}/>
        <input type="text" value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&sendMessage(input)} placeholder="Say it or type here..." className="flex-1 h-10 px-4 bg-gray-50 rounded-full text-sm outline-none border border-gray-200 focus:border-indigo-300"/>
        <button onClick={()=>sendMessage(input)} disabled={!input.trim()||isLoading} className="w-10 h-10 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center flex-shrink-0 disabled:opacity-40"><Send className="w-4 h-4 text-gray-600"/></button>
      </div>
    </div>
  )
}
