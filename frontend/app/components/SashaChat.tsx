'use client'
import { useState, useRef, useEffect, MutableRefObject } from 'react'
import { Loader2, ExternalLink } from 'lucide-react'
import { User, Itinerary } from '@/types'
import VoiceButton from './VoiceButton'
import { renderMarkdown } from '@/lib/markdown'
import { apiUrl, apiHeaders } from '@/lib/api'
import { CURRENT_USER } from '@/lib/currentUser'
import type { RichItinerary } from './ItineraryDays'
import IdeasPanel, { Idea } from './workspace/IdeasPanel'
import TripPanel from './workspace/TripPanel'
import YouPanel from './workspace/YouPanel'
import axios from 'axios'

interface Photo { url: string; thumb: string; description: string; photographer: string }

// Tab order is deliberate: Chat leads because this is a voice call and the transcript is what
// the guest follows; Ideas comes next because it's the way in when there's no plan yet; Trip
// is the outcome; You is reference. The old STARTER_ITINERARY placeholder is gone — a fake
// "7-Day Vietnam Discovery / $6,480" card was indistinguishable from a real plan, so a failed
// build left the guest reading invented numbers. TripPanel now shows an honest empty state.
const TABS: { id: WorkspaceTab; label: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'ideas', label: 'Ideas' },
  { id: 'trip', label: 'Trip' },
  { id: 'you', label: 'You' },
]

interface SashaChatProps {
  user: User
  // NOTE: the old `itinerary` / `onItineraryUpdate` pair is gone. Neither was ever read here,
  // so the page's `itinerary` state could never leave its initial value — which made the
  // checkout fallback `itinerary.total_fiat` a permanent 0 masquerading as a real amount.
  // `richItinerary` is the single source of truth for the plan.
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
  // Fired when a turn is taking long (slow specialist agent) so the avatar can speak a
  // short "one moment" filler instead of going silent. Not fired for fast turns.
  onThinking?: () => void
  // Fired when Sasha produces a full day-by-day itinerary.
  onItinerary?: (itinerary: any) => void
  // BCP-47-ish language code Sasha should reply in (en, vi, ko, zh, …).
  language?: string
  // Exposes sendMessage to the parent so quick-actions (budget/revise) can trigger a turn.
  registerSend?: (fn: (text: string) => void) => void
  // Lifted state — pass from parent to preserve history across remounts
  messages?: any[]
  setMessages?: React.Dispatch<React.SetStateAction<any[]>>
  // Live Workspace feed inputs — rendered as action cards in the stream.
  richItinerary?: RichItinerary | null
  photos?: Photo[]
  activePhoto?: number
  onSelectPhoto?: (i: number) => void
  onBook?: () => void
  // Bubbles the live STT socket connection state up to the page (for the call status pill).
  onVoiceConnected?: (connected: boolean) => void
  // Bubbles a mic/voice failure up so the call panel can show it, not just the composer.
  onMicError?: (message: string | null) => void
  // Fired when the conductor confirms the whole-trip booking (action: "trip_booked").
  onBooked?: (ref?: string) => void
  // Fired when the customer asks to book (action: "await_payment") — show the complete
  // itinerary and take payment. Booking is confirmed only after Stripe succeeds.
  onAwaitPayment?: () => void
  // The server's id for the stored trip. Checkout is priced from this, not from the browser.
  onItineraryId?: (id: string) => void
  // Set once payment is confirmed — turns the Trip tab's booking controls into "Reserved".
  bookingRef?: string | null
  // Which workspace tab is showing, and how to change it. Owned by the page so the tab
  // survives remounts and Sasha can nudge it (e.g. to Trip when a plan lands).
  activeTab?: WorkspaceTab
  onTabChange?: (tab: WorkspaceTab) => void
  // Tabs with something new since the user last looked — renders the gold dot.
  unseenTabs?: WorkspaceTab[]
  // Ideas live here rather than inside IdeasPanel because the panel unmounts every time the
  // guest leaves the tab; keeping them local meant a refetch (and a different three trips) on
  // every visit back. Lifted, they survive tab switches for the life of the session.
  ideasCache?: Idea[] | null
  onIdeasCache?: (ideas: Idea[]) => void
}

export type WorkspaceTab = 'chat' | 'ideas' | 'trip' | 'you'


export default function SashaChat({ user, onSashaResponse, onListeningChange, onPhotos, initialMessage, emptyState, avatarSpeaking, onInterrupt, presetPrompts, onSetGate, avatarSpeechGetter, isRespondingRef, readyToListen, onThinking, onItinerary, language = 'en', registerSend, messages: propMessages, setMessages: propSetMessages, richItinerary = null, photos = [], activePhoto = 0, onSelectPhoto, onBook, onVoiceConnected, onMicError, onBooked, onAwaitPayment, onItineraryId, bookingRef, activeTab = 'chat', onTabChange, unseenTabs = [], ideasCache, onIdeasCache }: SashaChatProps) {
  const tab = activeTab
  const [localMessages, setLocalMessages] = useState<any[]>(
    initialMessage ? [{ role: 'assistant', content: initialMessage }] : []
  )
  // Use lifted state when provided (persists across tab remounts), else fall back to local state
  const messages = propMessages !== undefined ? propMessages : localMessages
  const setMessages = propSetMessages ?? setLocalMessages

  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  // True while the "Build my custom trip" button's turn is in flight, so the button can
  // show a working state instead of looking like nothing happened.
  const [planning, setPlanning] = useState(false)
  // Itinerary accordion — which day numbers are expanded. Day 1 open by default; resets
  // whenever a fresh plan is built so the user lands on the top of the new itinerary.
  const [openDays, setOpenDays] = useState<Set<number>>(() => new Set([1]))
  const toggleDay = (day: number) => setOpenDays(prev => {
    const next = new Set(prev)
    if (next.has(day)) next.delete(day); else next.add(day)
    return next
  })
  // Reset on any real change to the plan, not just a renamed one. Keying this on the title
  // alone meant a revision that kept the name ("add a day", "make it more luxurious" — the
  // model usually keeps the trip name) left day 5 expanded on a plan that now has four days.
  const itineraryKey = richItinerary
    ? `${richItinerary.title}|${richItinerary.days?.length ?? 0}|${richItinerary.estimated_total_usd ?? 0}`
    : ''
  useEffect(() => { setOpenDays(new Set([1])) }, [itineraryKey])
  // Actionable booking surfaces for the latest turn.
  const [bookingLinks, setBookingLinks] = useState<{ label: string; url: string; type: string }[]>([])
  const [hotels, setHotels] = useState<{ name: string; stars: number; price_from: number; blurb: string; city: string; book_url: string; rating?: number; reviews?: number; tag?: string }[]>([])
  // Typed booking cards (flights, airport transfers, activities, restaurants) surfaced this
  // turn — real options from live web search, each deep-linking to the provider to complete.
  const [bookings, setBookings] = useState<{ type: string; title: string; dest?: string; options: { name: string; detail?: string; price?: string; book_url: string }[] }[]>([])
  // Single-flight guard: one conductor request at a time. Prevents duplicate STT
  // finals (or fast double-taps) from firing concurrent calls and stacking replies.
  const inFlightRef = useRef(false)
  // One stable id per chat (per mount = per "Tap to start" session) so the backend can group
  // this conversation's turns in the DB. Minted lazily on the first send (client-only crypto).
  const chatSessionIdRef = useRef<string>('')

  /**
   * Send a turn to the conductor.
   *
   * `force` marks a DELIBERATE action (a tap on "Build this", a preset chip, a typed
   * message) as opposed to a voice transcript. The responding-lock exists to stop Sasha's
   * own speech echoing back in through STT, but it can't tell an echo from a button press —
   * so without this, tapping a button while Sasha talks was silently swallowed (she talks
   * most of the time, so the Ideas buttons looked broken). A deliberate action interrupts
   * her instead, which is what a person expects: you pressed it, she stops and does it.
   */
  const sendMessage = async (content: string, opts?: { force?: boolean; intent?: string }) => {
    if (!content.trim()) return
    if (!chatSessionIdRef.current) {
      chatSessionIdRef.current = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : `sess-${Date.now()}-${Math.floor(Math.random() * 1e6)}`
    }
    if (isRespondingRef?.current) {
      if (!opts?.force) {
        console.log('[LOCK] ignoring transcript — Sasha is responding')
        return
      }
      console.log('[LOCK] force-released — deliberate action interrupts Sasha')
      onInterrupt?.()
      isRespondingRef.current = false
    }
    if (inFlightRef.current) {
      console.log('[Conductor] ignoring — a request is already in flight')
      return
    }
    inFlightRef.current = true
    const historyBeforeMessage = messages  // snapshot before appending
    setMessages(prev => [...prev, { role: 'user', content }])
    setInput('')
    setIsLoading(true)
    // If the conductor takes a LONG time (slow specialist agent), let the avatar offer a
    // brief acknowledgement so it isn't dead silent. Threshold kept high so normal turns
    // (which on this backend routinely run ~2-4s) do NOT trigger it — otherwise the avatar
    // says a filler on every single turn, which feels robotic. The page also rate-limits
    // how often a filler is actually spoken. Cleared as soon as the real response arrives.
    const thinkingTimer = setTimeout(() => onThinking?.(), 5000)
    try {
      const response = await axios.post(apiUrl('/api/agents/conductor'), {
        message: content,
        conversation_history: historyBeforeMessage,
        language,
        session_id: chatSessionIdRef.current,   // groups this chat's turns in the DB
        user_name: CURRENT_USER.firstName,       // so Sasha addresses the guest by name
        force_intent: opts?.intent,              // set when the UI knows the intent (idea build)
      }, { timeout: 60000, headers: apiHeaders() })  // bound the call so a hung backend can't stall the turn
      const { response: sashaResponse, conversation_history, photos: respPhotos, links, hotels: hotelRecs, bookings: bookingCards, itinerary, action, booking_ref, itinerary_id } = response.data
      // Replace local messages with server-authoritative history
      if (conversation_history?.length > 0) {
        setMessages(conversation_history)
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: sashaResponse }])
      }
      if (onSashaResponse) onSashaResponse(sashaResponse)
      if (respPhotos?.length > 0) onPhotos?.(respPhotos)
      setBookingLinks(Array.isArray(links) ? links : [])
      setHotels(Array.isArray(hotelRecs) ? hotelRecs : [])
      setBookings(Array.isArray(bookingCards) ? bookingCards : [])
      if (itinerary?.days?.length) onItinerary?.(itinerary)
      if (itinerary_id) onItineraryId?.(itinerary_id)
      // The customer asked to book: show the full itinerary and take payment. A booking is
      // confirmed ONLY by /api/payments/verify against a real Stripe session.
      //
      // There is deliberately no `trip_booked` branch. It used to exist as a compatibility
      // shim and called onBooked() directly — which manufactured a confirmed booking, with a
      // share sheet and PDF, without any payment. Any backend that still emits it is wrong,
      // and the safe response is to ignore it rather than to invent a sale.
      if (action === 'await_payment') onAwaitPayment?.()
      else if (action === 'trip_booked') console.warn('[Conductor] ignoring legacy trip_booked: bookings require verified payment')
    } catch (error: any) {
      console.error('[Conductor] error:', error?.response?.status, error?.response?.data, error?.message)
      // Speak a graceful fallback so the avatar is never silent on a backend hiccup —
      // this is what "the avatar doesn't respond" looked like to the user.
      const fallback = "Sorry, I didn't quite catch that — could you say it again?"
      setMessages(prev => [...prev, { role: 'assistant', content: fallback }])
      onSashaResponse?.(fallback)
    } finally {
      clearTimeout(thinkingTimer)
      setIsLoading(false)
      inFlightRef.current = false
    }
  }

  // Expose the latest sendMessage to the parent (for budget/revise quick-actions).
  const sendRef = useRef(sendMessage)
  sendRef.current = sendMessage
  useEffect(() => { registerSend?.((t: string) => sendRef.current(t)) }, [])

  const travellerCount = user.travellers?.length || 2
  // The caption of the photo currently on screen. Only ever use this to label the PHOTO —
  // the carousel rotates every 5s, so anything else it labels will silently rename itself.
  const activeDest = photos[activePhoto]?.description || 'Vietnam'

  // Where the recommended stays actually are, taken from the stays themselves. The header
  // used to read `activeDest`, so "Hand-picked for Hoi An ancient town" changed every few
  // seconds as the photos cycled while the hotels underneath stayed put — naming a city the
  // hotels weren't even in. A label has to come from the thing it labels.
  const hotelsDest = (() => {
    const cities = Array.from(new Set(hotels.map(h => h.city).filter(Boolean)))
    if (cities.length === 0) return ''
    if (cities.length === 1) return cities[0]
    if (cities.length === 2) return `${cities[0]} and ${cities[1]}`
    return `${cities[0]}, ${cities[1]} and ${cities.length - 2} more`
  })()

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Workspace tabs — one job per tab. Chat leads: this is a voice call, so the
           transcript is the thing the guest follows; the rest is theirs to pull, not ours
           to push. Sasha marks a tab with a dot instead of yanking them off the call. ── */}
      <nav className="lw-tabs" role="tablist">
        {TABS.map(t => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`lw-tab ${tab === t.id ? 'on' : ''}`}
            onClick={() => onTabChange?.(t.id)}
          >
            {t.label}
            {tab !== t.id && unseenTabs.includes(t.id) && <span className="lw-ping" aria-label="Updated" />}
          </button>
        ))}
      </nav>

      {tab === 'ideas' && (
        <IdeasPanel
          user={user}
          building={isLoading}
          cached={ideasCache}
          onLoaded={onIdeasCache}
          // Tapping an idea IS an itinerary request — say so explicitly rather than letting
          // keyword classification guess (it mis-routed these to the activity agent).
          onBuild={(prompt) => sendMessage(prompt, { force: true, intent: 'itinerary' })}
        />
      )}

      {tab === 'trip' && (
        <TripPanel
          richItinerary={richItinerary}
          openDays={openDays}
          toggleDay={toggleDay}
          onBook={onBook}
          travellerCount={travellerCount}
          onBrowseIdeas={() => onTabChange?.('ideas')}
          bookingRef={bookingRef}
        />
      )}

      {tab === 'you' && (
        <YouPanel user={user} plannedThisSession={richItinerary ? 1 : 0} language={language} />
      )}

      {tab === 'chat' && (
      <div className="lw-stream">

        {/* ── Conversation transcript ── */}
        {messages.length > 0 && <div className="lw-when">Conversation</div>}
        {messages.length === 0 && emptyState}
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`} style={{ flex: '0 0 auto' }}>
            <div className={`w-8 h-8 rounded-2xl flex items-center justify-center flex-shrink-0 text-xs font-medium ${
              msg.role === 'assistant'
                ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white'
                : 'bg-white/10 text-white/60'
            }`}>
              {msg.role === 'assistant' ? 'S' : (user.display_name?.[0] || 'Y')}
            </div>
            <div className="max-w-[88%]">
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
          <div className="flex gap-3" style={{ flex: '0 0 auto' }}>
            <div className="w-8 h-8 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs">S</div>
            <div className="px-4 py-3 rounded-2xl bg-white/5 border border-white/5">
              <Loader2 className="w-4 h-4 animate-spin text-white/40" />
            </div>
          </div>
        )}

        {/* ── Stays / flights / transfers / activities surfaced this turn (context-driven).
             These belong with the conversation: they're what Sasha just found in answer to
             what was said, so they sit under the newest message rather than in a tab. ── */}
        {(hotels.length > 0 || bookings.length > 0 || bookingLinks.length > 0) && (
          <>
            <div className="lw-when">Found for you</div>
            {bookings.map((b, bi) => {
              const meta: Record<string, { icon: string; label: string; ci: string }> = {
                flight: { icon: '✈️', label: 'Flights', ci: 'blue' },
                cab: { icon: '🚕', label: 'Airport transfers', ci: 'gold' },
                activity: { icon: '🎟️', label: 'Things to do', ci: 'purple' },
                restaurant: { icon: '🍽️', label: 'Restaurants', ci: 'gold' },
              }
              const m = meta[b.type] || { icon: '🔗', label: 'Booking', ci: 'gold' }
              return (
                <div className="lw-card" key={`bk-${bi}`}>
                  <div className="lw-cardHd">
                    <span className={`lw-ci ${m.ci}`}>{m.icon}</span>
                    <div className="lw-meta">
                      <div className="lw-k">{m.label}</div>
                      <div className="lw-h">{b.title}</div>
                    </div>
                  </div>
                  <div className="lw-cardBody">
                    {b.options.map((o, oi) => (
                      <div className="lw-opt" key={oi}>
                        <span className="logo">{m.icon}</span>
                        <div className="od">
                          <div className="o1">{o.name}</div>
                          <div className="o2">{[o.detail, o.price].filter(Boolean).join(' · ')}</div>
                        </div>
                        <a className="price" href={o.book_url} target="_blank" rel="noopener noreferrer">Book</a>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
            {hotels.length > 0 && (
              <div className="lw-card">
                <div className="lw-cardHd">
                  <span className="lw-ci purple">🏨</span>
                  <div className="lw-meta">
                    <div className="lw-k">Recommended stays</div>
                    <div className="lw-h">{hotelsDest ? `Hand-picked for ${hotelsDest}` : 'Hand-picked for you'}</div>
                  </div>
                </div>
                <div className="lw-cardBody">
                  {hotels.map((h, i) => (
                    <div className="lw-opt" key={i}>
                      <span className="logo">🏨</span>
                      <div className="od">
                        <div className="o1">{h.name}</div>
                        <div className="o2">{'★'.repeat(h.stars)} · from ${h.price_from}/night{h.rating ? ` · ${h.rating}/10` : (h.city ? ` · ${h.city}` : '')}</div>
                        {h.tag && <span className="tag">{h.tag}</span>}
                      </div>
                      <a className="price" href={h.book_url} target="_blank" rel="noopener noreferrer">Book</a>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {bookingLinks.length > 0 && (
              <div className="lw-card">
                <div className="lw-cardHd">
                  <span className="lw-ci gold">🔗</span>
                  <div className="lw-meta">
                    <div className="lw-k">Quick booking</div>
                    <div className="lw-h">Reserve in one tap</div>
                  </div>
                </div>
                <div className="lw-cardBody">
                  <div className="lw-chips">
                    {bookingLinks.map((l, i) => (
                      <a key={i} className="lw-chip" href={l.url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                        <ExternalLink className="w-3 h-3" />{l.label}
                      </a>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* ── What Sasha is showing right now — destination photos update every turn ── */}
        {photos.length > 0 && (
          <>
            <div className="lw-when">Right now</div>
            <div className="lw-card">
              <div className="lw-cardBody" style={{ padding: 14 }}>
                <div className="lw-photohero">
                  <img key={activePhoto} src={photos[activePhoto]?.url} alt={activeDest} />
                  <div className="lw-photohero-grad" />
                  <div className="lw-photohero-cap">
                    <div className="lw-photohero-k">Exploring</div>
                    <div className="lw-photohero-title">{activeDest}</div>
                    {photos[activePhoto]?.photographer && (
                      <div className="lw-photohero-by">📷 {photos[activePhoto].photographer}</div>
                    )}
                  </div>
                </div>
                {photos.length > 1 && (
                  <div className="lw-gal" style={{ marginTop: 10 }}>
                    {photos.slice(0, 4).map((p, i) => (
                      <img
                        key={i}
                        src={p.thumb || p.url}
                        alt={p.description}
                        onClick={() => onSelectPhoto?.(i)}
                        style={{ outline: i === activePhoto ? '2px solid #DAA520' : 'none', outlineOffset: -1 }}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
      )}

      {/* ── Composer ── */}
      <div className="lw-composer">
        <div className="field">
          <VoiceButton
            // Speaking pulls the guest back to Chat: they're talking to Sasha, and her reply
            // (plus whatever she surfaces — stays, tours, prices) lands there. Leaving them
            // parked on Ideas meant Sasha answered into a tab they couldn't see.
            onTranscript={(text) => { onTabChange?.('chat'); sendMessage(text) }}
            autoStart={true}
            readyToListen={readyToListen}
            avatarSpeaking={avatarSpeaking}
            onInterrupt={onInterrupt}
            onSetGate={onSetGate}
            avatarSpeechGetter={avatarSpeechGetter}
            language={language}
            onSpeakingChange={onListeningChange}
            onConnectedChange={onVoiceConnected}
            onMicError={onMicError}
          />
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), sendMessage(input, { force: true }))}
            placeholder="Ask Sasha anything…  (or just talk)"
          />
          {presetPrompts?.slice(0, 2).map(prompt => (
            <button key={prompt} className="lw-chip" onClick={() => sendMessage(prompt, { force: true })}>{prompt}</button>
          ))}
          <button className="lw-send" onClick={() => sendMessage(input, { force: true })} disabled={!input.trim() || isLoading}>➤</button>
        </div>
      </div>

      <style jsx global>{`
        .lw-stream{flex:1;min-height:0;overflow-y:auto;padding:18px 18px 24px;display:flex;flex-direction:column;gap:13px}
        /* Flex children shrink by default: without this, cards collapse to hairlines as soon
           as the column overflows (which read as a "stretched" panel). */
        .lw-stream > *{flex-shrink:0}
        .lw-stream::-webkit-scrollbar{width:8px}
        .lw-stream::-webkit-scrollbar-thumb{background:rgba(255,255,255,.08);border-radius:8px}

        /* ── Tabs ── */
        .lw-tabs{flex-shrink:0;display:flex;gap:4px;padding:10px 14px 0;border-bottom:1px solid rgba(255,255,255,.07)}
        .lw-tab{position:relative;display:flex;align-items:center;gap:7px;background:none;border:0;cursor:pointer;font:inherit;font-size:13px;font-weight:500;color:rgba(255,255,255,.34);padding:9px 14px 12px;border-radius:10px 10px 0 0;transition:color .18s}
        .lw-tab:hover{color:rgba(255,255,255,.62)}
        .lw-tab.on{color:#E8B923}
        .lw-tab.on::after{content:"";position:absolute;left:12px;right:12px;bottom:-1px;height:2px;background:#DAA520;border-radius:2px 2px 0 0}
        .lw-tab:focus-visible{outline:2px solid #DAA520;outline-offset:-2px}
        .lw-ping{width:6px;height:6px;border-radius:50%;background:#DAA520;animation:lwPing 2s infinite}
        @keyframes lwPing{0%,100%{opacity:.4}50%{opacity:1}}

        /* ── Trip summary bar ── */
        .lw-summary{flex-shrink:0;display:flex;align-items:center;gap:22px;padding:12px 18px;border-bottom:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.28)}
        .lw-sumcell{display:flex;flex-direction:column;gap:3px}
        .lw-sumcell.tot{margin-left:auto;align-items:flex-end}
        .lw-sumcell .k{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.34)}
        .lw-sumcell .v{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
        .lw-sumcell .amt{font-family:'Playfair Display',Georgia,serif;font-size:22px;color:#E8B923;font-variant-numeric:tabular-nums}

        /* ── Empty states ── */
        .lw-empty{margin:auto;text-align:center;display:flex;flex-direction:column;align-items:center;gap:9px;padding:30px 20px;max-width:340px}
        .lw-empty-ic{font-size:30px;opacity:.5}
        .lw-empty-t{font-size:15px;font-weight:600}
        .lw-empty-s{font-size:12.5px;color:rgba(255,255,255,.45);line-height:1.55}
        .lw-empty-cta{margin-top:6px;border:1px solid rgba(218,165,32,.3);background:rgba(218,165,32,.12);color:#E8B923;cursor:pointer;font:inherit;font-size:12.5px;font-weight:600;padding:10px 16px;border-radius:11px}
        .lw-empty-cta:hover{background:rgba(218,165,32,.2)}
        .lw-note-s{font-size:11px;color:rgba(255,255,255,.34)}

        /* ── Ideas ── */
        .lw-lead{font-size:12.5px;color:rgba(255,255,255,.62);line-height:1.55;max-width:60ch;margin:0 2px}
        .lw-refresh{margin-left:auto;background:none;border:0;color:rgba(255,255,255,.34);cursor:pointer;font-size:13px;padding:2px 6px;border-radius:6px}
        .lw-refresh:hover{color:#DAA520}
        .lw-when .lw-refresh + ::after{display:none}
        .lw-idea{display:flex;border:1px solid rgba(255,255,255,.09);border-radius:16px;overflow:hidden;background:rgba(255,255,255,.02);transition:border-color .18s,transform .18s;animation:lwIn .5s cubic-bezier(.2,.8,.2,1) both}
        .lw-idea:hover{border-color:rgba(218,165,32,.3);transform:translateY(-2px)}
        /* Fixed-width art panel — it cannot stretch however wide the workspace gets. The
           gradient is the fallback ground, visible when no photo came back. */
        .lw-idea-art{width:120px;flex-shrink:0;position:relative;overflow:hidden}
        .lw-idea-art img{width:100%;height:100%;object-fit:cover;display:block}
        .lw-idea-art::after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent 55%,rgba(10,10,18,.55))}
        .lw-idea-art.art1{background:linear-gradient(150deg,#4a3820,#8a6626 60%,#33283a)}
        .lw-idea-art.art2{background:linear-gradient(150deg,#123028,#227a5c 60%,#173743)}
        .lw-idea-art.art3{background:linear-gradient(150deg,#2b1f36,#63456f 60%,#26334a)}
        .lw-idea-b{padding:13px 14px;display:flex;flex-direction:column;gap:7px;min-width:0;flex:1}
        .lw-idea-hd{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
        .lw-idea-b h3{font-size:14.5px;font-weight:600}
        .lw-idea-tag{font-size:9.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#12101b;background:#E8B923;padding:3px 8px;border-radius:99px}
        .lw-idea-b p{font-size:12.5px;color:rgba(255,255,255,.62);line-height:1.5}
        .lw-idea-why{font-size:11.5px;color:#DAA520}
        .lw-idea-f{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:1px}
        .lw-idea-chips{display:flex;gap:6px;flex-wrap:wrap}
        .lw-idea-chips i{font-style:normal;font-size:10.5px;color:rgba(255,255,255,.34);background:rgba(255,255,255,.05);padding:4px 9px;border-radius:99px}
        .lw-idea-price{margin-left:auto;font-family:'Playfair Display',Georgia,serif;font-size:16px;color:#E8B923;font-variant-numeric:tabular-nums}
        .lw-idea-cta{border:1px solid rgba(218,165,32,.3);background:rgba(218,165,32,.12);color:#E8B923;cursor:pointer;font:inherit;font-size:12px;font-weight:600;padding:8px 13px;border-radius:9px;white-space:nowrap}
        .lw-idea-cta:hover:not(:disabled){background:rgba(218,165,32,.2)}
        .lw-idea-cta:disabled{opacity:.5;cursor:default}
        .lw-idea-skel{height:104px;border-radius:16px;background:linear-gradient(90deg,rgba(255,255,255,.03),rgba(255,255,255,.07),rgba(255,255,255,.03));background-size:200% 100%;animation:lwShimmer 1.4s infinite}
        @keyframes lwShimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}

        /* ── You ── */
        .lw-who{display:flex;align-items:center;gap:12px;padding:14px;border:1px solid rgba(255,255,255,.09);border-radius:16px;background:rgba(255,255,255,.02)}
        .lw-who-av{width:42px;height:42px;border-radius:50%;background:linear-gradient(135deg,#8b5cf6,#6d28d9);display:grid;place-items:center;font-weight:700;font-size:14px;flex-shrink:0}
        .lw-who-m{min-width:0;flex:1}
        .lw-who-n{font-size:15px;font-weight:600}
        .lw-who-e{font-size:11.5px;color:rgba(255,255,255,.34);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .lw-who-tier{font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#DAA520;background:rgba(218,165,32,.12);border:1px solid rgba(218,165,32,.3);padding:4px 9px;border-radius:99px}
        .lw-stats{display:flex;gap:9px}
        .lw-stat{flex:1;display:flex;flex-direction:column;gap:3px;align-items:center;padding:12px 8px;border:1px solid rgba(255,255,255,.07);border-radius:14px;background:rgba(255,255,255,.02)}
        .lw-stat .v{font-size:19px;font-weight:600;color:#E8B923;font-variant-numeric:tabular-nums}
        .lw-stat .k{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:rgba(255,255,255,.34);text-align:center}
        .lw-prefchips{display:flex;flex-wrap:wrap;gap:7px}
        .lw-prefchip{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,.8);background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);border-radius:99px;padding:6px 12px}
        .lw-prefchip b{font-weight:600;color:rgba(255,255,255,.34);font-size:10px;letter-spacing:.06em;text-transform:uppercase}
        .lw-past{list-style:none;display:flex;flex-direction:column;gap:2px;margin:0;padding:0}
        .lw-past li{display:flex;gap:14px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.06)}
        .lw-past li:last-child{border-bottom:0}
        .lw-past .yr{font-size:11px;color:rgba(255,255,255,.34);width:88px;flex-shrink:0;padding-top:2px}
        .lw-past .pt{font-size:13px;font-weight:500}
        .lw-past .ps{font-size:11.5px;color:rgba(255,255,255,.34);margin-top:2px}
        .lw-tripref{font-size:10px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#DAA520;background:rgba(218,165,32,.1);border:1px solid rgba(218,165,32,.25);border-radius:6px;padding:3px 7px;align-self:flex-start;white-space:nowrap}

        /* Booked state — replaces every "Book" affordance once the trip is paid for. */
        .lw-hotel-reserved{font-size:11.5px;font-weight:600;color:#34d399;background:rgba(52,211,153,.12);border:1px solid rgba(52,211,153,.3);border-radius:8px;padding:6px 11px;white-space:nowrap}
        .lw-bookedBanner{display:flex;align-items:center;justify-content:center;gap:8px;padding:13px;border-radius:13px;font-size:13.5px;font-weight:600;color:#34d399;background:rgba(52,211,153,.1);border:1px solid rgba(52,211,153,.35);font-variant-numeric:tabular-nums}
        .lw-when{flex:0 0 auto;display:flex;align-items:center;gap:12px;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.35);margin:8px 2px 0}
        .lw-when:first-child{margin-top:0}
        .lw-when::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,rgba(255,255,255,.12),transparent)}
        .lw-card{flex:0 0 auto;border-radius:20px;border:1px solid rgba(255,255,255,.09);overflow:hidden;background:linear-gradient(180deg,rgba(255,255,255,0.055),rgba(255,255,255,0.022));box-shadow:0 16px 40px -24px rgba(0,0,0,.9);animation:lwIn .5s cubic-bezier(.2,.8,.2,1) both}
        @keyframes lwIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
        .lw-card.fresh{position:relative;border-color:rgba(218,165,32,.5);background:linear-gradient(180deg,rgba(218,165,32,0.11),rgba(255,255,255,0.025));box-shadow:0 0 0 1px rgba(218,165,32,.2),0 24px 60px -26px rgba(218,165,32,.5)}
        .lw-card.fresh::before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:3px;border-radius:0 3px 3px 0;background:linear-gradient(180deg,#E8B923,#DAA520)}
        .lw-cardHd{display:flex;align-items:center;gap:12px;padding:15px 18px 12px}
        .lw-ci{width:34px;height:34px;border-radius:11px;display:grid;place-items:center;font-size:16px;flex-shrink:0}
        .lw-ci.gold{background:rgba(218,165,32,0.12);color:#DAA520;box-shadow:inset 0 0 0 1px rgba(218,165,32,.25)}
        .lw-ci.blue{background:rgba(96,165,250,.14);color:#93c5fd;box-shadow:inset 0 0 0 1px rgba(96,165,250,.22)}
        .lw-ci.green{background:rgba(52,211,153,.14);color:#6ee7b7;box-shadow:inset 0 0 0 1px rgba(52,211,153,.22)}
        .lw-ci.purple{background:rgba(167,139,250,.16);color:#c4b5fd;box-shadow:inset 0 0 0 1px rgba(167,139,250,.24)}
        .lw-meta{flex:1;min-width:0}
        .lw-k{font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:rgba(255,255,255,.4)}
        .lw-h{font-size:16px;font-weight:600;margin-top:3px;letter-spacing:-.01em;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .lw-ribbon{font-size:9.5px;font-weight:700;letter-spacing:.1em;color:#1a1205;background:linear-gradient(135deg,#E8B923,#DAA520);flex-shrink:0;padding:5px 10px;border-radius:8px;display:flex;align-items:center;gap:5px;box-shadow:0 4px 14px -4px rgba(218,165,32,.6)}
        .lw-cardBody{padding:0 18px 16px}
        .lw-photohero{position:relative;height:184px;border-radius:14px;overflow:hidden;border:1px solid rgba(255,255,255,.08)}
        .lw-photohero img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;animation:lwFade .6s ease}
        @keyframes lwFade{from{opacity:.25}to{opacity:1}}
        .lw-photohero-grad{position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.85),transparent 62%)}
        .lw-photohero-cap{position:absolute;left:16px;right:16px;bottom:13px}
        .lw-photohero-k{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.65)}
        .lw-photohero-title{font-size:20px;font-weight:600;color:#fff;margin-top:3px;letter-spacing:-.01em}
        .lw-photohero-by{font-size:11px;color:rgba(255,255,255,.6);margin-top:4px}
        .lw-flights{display:flex;align-items:center;gap:11px;padding:11px 12px;border-radius:13px;background:rgba(96,165,250,.08);border:1px solid rgba(96,165,250,.22);text-decoration:none;margin-bottom:11px;transition:.15s}
        .lw-flights:hover{border-color:rgba(96,165,250,.45);background:rgba(96,165,250,.12)}
        .lw-flights-ic{width:30px;height:30px;border-radius:8px;background:rgba(96,165,250,.14);display:grid;place-items:center;font-size:14px;flex-shrink:0}
        .lw-flights-meta{flex:1;min-width:0}
        .lw-flights-k{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.4)}
        .lw-flights-h{font-size:13.5px;font-weight:600;color:#fff;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .lw-flights-cta{font-size:12px;font-weight:600;color:#93c5fd;white-space:nowrap;flex-shrink:0}
        .lw-mapwrap{margin-bottom:13px}
        .lw-galmini{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}
        .lw-galmini img{width:100%;height:52px;object-fit:cover;border-radius:9px;border:1px solid rgba(255,255,255,.08);display:block;cursor:pointer;transition:.15s}
        .lw-galmini img:hover{transform:translateY(-2px)}
        .lw-dayrow{display:flex;align-items:center;gap:13px;padding:11px 0;border-top:1px solid rgba(255,255,255,.06)}
        .lw-dayrow .num{width:30px;height:30px;border-radius:9px;background:rgba(218,165,32,0.12);display:grid;place-items:center;font-size:12px;font-weight:700;color:#DAA520;flex-shrink:0;box-shadow:inset 0 0 0 1px rgba(218,165,32,.22)}
        .lw-dayrow .info{min-width:0}
        .lw-dayrow .info .d{font-size:14px;font-weight:500;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .lw-dayrow .info .s{font-size:12px;color:rgba(255,255,255,.5);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .lw-dayrow .px{margin-left:auto;font-size:11.5px;color:rgba(255,255,255,.3);white-space:nowrap;padding-left:10px}
        .lw-day{border-top:1px solid rgba(255,255,255,.07)}
        .lw-day:first-of-type{border-top:none}
        .lw-day-hd{display:flex;align-items:center;gap:12px;width:100%;background:none;border:none;cursor:pointer;text-align:left;padding:13px 0;color:inherit;font:inherit}
        .lw-day-hd:hover .lw-day-title{color:#f5d77a}
        .lw-day .num{width:30px;height:30px;border-radius:9px;background:rgba(218,165,32,0.12);display:grid;place-items:center;font-size:12px;font-weight:700;color:#DAA520;flex-shrink:0;box-shadow:inset 0 0 0 1px rgba(218,165,32,.22)}
        .lw-day-meta{flex:1;min-width:0}
        .lw-day-title{font-size:14.5px;font-weight:600;color:#fff;letter-spacing:-.01em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;transition:color .15s}
        .lw-day-city{font-size:12px;color:rgba(255,255,255,.5);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .lw-day-right{display:flex;align-items:center;gap:10px;flex-shrink:0}
        .lw-day-tag{font-size:11px;color:rgba(255,255,255,.3);white-space:nowrap}
        .lw-chev{font-size:14px;color:rgba(255,255,255,.45);transition:transform .2s;line-height:1}
        .lw-chev.open{transform:rotate(180deg)}
        .lw-day-detail{padding:2px 0 14px 42px;animation:lwFade .35s ease}
        .lw-day-imgwrap{border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,.08);margin-bottom:11px}
        .lw-day-img{width:100%;height:150px;object-fit:cover;display:block}
        .lw-day-desc{font-size:12.5px;color:rgba(255,255,255,.6);line-height:1.55;margin-bottom:11px}
        .lw-acts{display:flex;flex-direction:column;gap:7px}
        .lw-act{display:flex;gap:10px;text-decoration:none;align-items:flex-start;padding:9px 11px;border-radius:10px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.05);transition:.15s}
        .lw-act:hover{border-color:rgba(218,165,32,.3);background:rgba(218,165,32,.05)}
        .lw-act-time{font-size:9.5px;letter-spacing:.05em;text-transform:uppercase;color:#DAA520;background:rgba(218,165,32,.1);border:1px solid rgba(218,165,32,.2);padding:4px 7px;border-radius:6px;white-space:nowrap;flex-shrink:0;margin-top:1px}
        .lw-act-body{min-width:0}
        .lw-act-name{font-size:13px;color:rgba(255,255,255,.92);font-weight:500;display:flex;align-items:center;gap:5px}
        .lw-act-ext{font-size:11px;color:rgba(255,255,255,.35)}
        .lw-act-blurb{font-size:11.5px;color:rgba(255,255,255,.45);margin-top:3px;line-height:1.45}
        .lw-hotel{display:flex;align-items:center;gap:11px;margin-top:9px;padding:11px 12px;border-radius:12px;background:rgba(218,165,32,0.07);border:1px solid rgba(218,165,32,.2)}
        .lw-hotel-ic{width:30px;height:30px;border-radius:8px;background:rgba(218,165,32,.12);display:grid;place-items:center;font-size:14px;flex-shrink:0}
        .lw-hotel-meta{flex:1;min-width:0}
        .lw-hotel-k{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.4)}
        .lw-hotel-name{font-size:13.5px;font-weight:600;color:#fff;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .lw-hotel-rating{font-size:11px;color:#E8B923;margin-top:2px}
        .lw-hotel-price{font-size:11.5px;color:rgba(255,255,255,.7);margin-top:2px;font-weight:500}
        .lw-breakdown{display:flex;flex-wrap:wrap;gap:7px 14px;margin-top:11px;font-size:11.5px;color:rgba(255,255,255,.5)}
        .lw-breakdown span{white-space:nowrap}
        .lw-hotel-book{font-size:12px;font-weight:600;color:#fff;background:linear-gradient(135deg,#DAA520,#B8860B);padding:8px 14px;border-radius:9px;text-decoration:none;flex-shrink:0;transition:.15s}
        .lw-hotel-book:hover{filter:brightness(1.08)}
        .lw-totalRow{display:flex;align-items:center;justify-content:space-between;margin-top:14px;padding-top:14px;border-top:1px solid rgba(255,255,255,.08)}
        .lw-totalRow .lab{font-size:12px;color:rgba(255,255,255,.5)}
        .lw-totalRow .amt{font-family:'Playfair Display',Georgia,serif;font-size:26px;color:#E8B923}
        .lw-bookBtn{margin-top:14px;width:100%;padding:13px;border:none;border-radius:13px;cursor:pointer;font-size:14px;font-weight:600;color:#fff;background:linear-gradient(135deg,#DAA520,#B8860B);box-shadow:0 10px 30px -12px rgba(218,165,32,.6);transition:.2s}
        .lw-bookBtn:hover:not(:disabled){filter:brightness(1.08);transform:translateY(-1px)}
        .lw-bookBtn:disabled{opacity:.65;cursor:default}
        .lw-booknote{font-size:11px;color:rgba(255,255,255,.35);text-align:center;margin-top:8px}
        .lw-gal{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
        .lw-gal img{width:100%;height:72px;object-fit:cover;border-radius:12px;border:1px solid rgba(255,255,255,.08);display:block;cursor:pointer;transition:.2s}
        .lw-gal img:hover{transform:translateY(-2px)}
        .lw-opt{display:flex;align-items:center;gap:13px;padding:12px;border:1px solid rgba(255,255,255,.08);border-radius:14px;margin-top:9px;background:rgba(255,255,255,.02)}
        .lw-opt:first-of-type{margin-top:0;border-color:rgba(218,165,32,.4);background:rgba(218,165,32,0.10)}
        .lw-opt .logo{width:36px;height:36px;border-radius:10px;background:rgba(255,255,255,.06);display:grid;place-items:center;font-size:16px;flex-shrink:0}
        .lw-opt .od{flex:1;min-width:0}
        .lw-opt .o1{font-size:14px;font-weight:500;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .lw-opt .o2{font-size:12px;color:rgba(255,255,255,.5);margin-top:3px}
        .lw-opt .price{font-weight:700;font-size:13px;color:#E8B923;white-space:nowrap;text-decoration:none;border:1px solid rgba(218,165,32,.4);padding:8px 13px;border-radius:10px;transition:.2s}
        .lw-opt .price:hover{background:rgba(218,165,32,.12)}
        .lw-opt .tag{font-size:10px;color:#DAA520;border:1px solid rgba(218,165,32,.4);border-radius:6px;padding:3px 7px;margin-top:6px;display:inline-block}
        .lw-prefrow{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 13px;border-radius:11px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05)}
        .lw-prefk{font-size:11px;letter-spacing:.04em;text-transform:capitalize;color:rgba(255,255,255,.4)}
        .lw-prefv{font-size:13px;color:rgba(255,255,255,.82);text-transform:capitalize;text-align:right}
        .lw-composer{flex-shrink:0;padding:14px 16px;border-top:1px solid rgba(255,255,255,0.07);background:rgba(0,0,0,.2)}
        .lw-composer .field{display:flex;align-items:center;gap:9px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:8px 10px 8px 12px}
        .lw-composer .field input{flex:1;min-width:60px;background:transparent;border:none;outline:none;color:#fff;font-size:13.5px;font-family:inherit}
        .lw-composer .field input::placeholder{color:rgba(255,255,255,.3)}
        .lw-send{width:38px;height:38px;border-radius:12px;border:none;cursor:pointer;background:linear-gradient(135deg,#DAA520,#B8860B);color:#fff;display:grid;place-items:center;font-size:15px;flex-shrink:0;transition:.2s}
        .lw-send:hover:not(:disabled){filter:brightness(1.08)}
        .lw-send:disabled{opacity:.4;cursor:default}
        .lw-chip{font-size:11.5px;color:rgba(255,255,255,.6);border:1px solid rgba(255,255,255,0.1);border-radius:999px;padding:7px 12px;cursor:pointer;white-space:nowrap;transition:.2s;background:rgba(255,255,255,.02);flex-shrink:0}
        .lw-chip:hover{border-color:rgba(218,165,32,.4);color:#DAA520}
      `}</style>
    </div>
  )
}
