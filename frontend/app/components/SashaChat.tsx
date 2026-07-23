'use client'
import { useState, useRef, useEffect, MutableRefObject } from 'react'
import { Loader2, ExternalLink } from 'lucide-react'
import { User, Itinerary } from '@/types'
import VoiceButton, { MicDevicesInfo } from './VoiceButton'
import { renderMarkdown } from '@/lib/markdown'
import { apiUrl, apiHeaders } from '@/lib/api'
import { CURRENT_USER } from '@/lib/currentUser'
import type { RichItinerary } from './ItineraryDays'
import IdeasPanel, { Idea } from './workspace/IdeasPanel'
import TripPanel from './workspace/TripPanel'
import YouPanel from './workspace/YouPanel'
import axios from 'axios'

// `description` is the photographer's free-text Unsplash caption ("Colors", "4:51pm") — never
// use it as a place name. `location` is the actual destination, stamped on by the foto agent.
interface Photo { url: string; thumb: string; description: string; photographer: string; location?: string; unsplash_url?: string }

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
  // Context-driven interim line for the avatar to speak while a slow turn runs (chosen from the
  // classified intent). Empty/omitted = stay silent.
  onThinking?: (line: string) => void
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
  // Hands the mic-device picker up to the page, which renders it as a pill beside the camera
  // toggle in the call panel rather than leaving a bare <select> under the composer.
  onMicDevices?: (info: MicDevicesInfo | null) => void
  // Fired when the conductor confirms the whole-trip booking (action: "trip_booked").
  onBooked?: (ref?: string) => void
  // Fired when the customer asks to book (action: "await_payment") — show the complete
  // itinerary and take payment. Booking is confirmed only after Stripe succeeds.
  onAwaitPayment?: () => void
  // Fired when the guest taps "Book & Pay" on an individual hotel/flight/cab card. The parent
  // opens the same payment modal and checks out by offer_id (server-priced, like the trip).
  onBookItem?: (offer: { offer_id: string; label: string; amount_usd: number; kind: string; name: string }) => void
  // The server's id for the stored trip. Checkout is priced from this, not from the browser.
  onItineraryId?: (id: string) => void
  // Set once payment is confirmed — turns the Trip tab's booking controls into "Reserved".
  bookingRef?: string | null
  // Which workspace tab is showing, and how to change it. Owned by the page so the tab
  // survives remounts and Sasha can nudge it (e.g. to Trip when a plan lands).
  activeTab?: WorkspaceTab
  onTabChange?: (tab: WorkspaceTab) => void
  // Flag a tab as having new content WITHOUT navigating there. The page already had this
  // (`markUnseen`) but never handed it to the chat, so the voice path had no way to say
  // "there's a reply waiting" other than yanking the guest to Chat mid-task.
  onMarkUnseen?: (tab: WorkspaceTab) => void
  // Fired when an itinerary build starts/ends. The page owns the mic gate (it sits next to the
  // avatar's speak-driven gating), so it does the muting — this only reports the state.
  onBuildingChange?: (building: boolean) => void
  // Tabs with something new since the user last looked — renders the gold dot.
  unseenTabs?: WorkspaceTab[]
  // Ideas live here rather than inside IdeasPanel because the panel unmounts every time the
  // guest leaves the tab; keeping them local meant a refetch (and a different three trips) on
  // every visit back. Lifted, they survive tab switches for the life of the session.
  ideasCache?: Idea[] | null
  onIdeasCache?: (ideas: Idea[]) => void
}

export type WorkspaceTab = 'chat' | 'ideas' | 'trip' | 'you'

// Context-driven interim speech. While a slow search/build runs, Sasha says what she is ACTUALLY
// doing — chosen from the turn's classified intent — never a random filler. Only the slow,
// card-producing intents get a line; general chat and photos are fast, so she stays silent rather
// than padding a quick turn. Two on-topic variants each so back-to-back searches don't repeat
// word-for-word. A build outranks the domain lines when several intents fire on one turn.
const INTERIM_LINES: Record<string, string[]> = {
  itinerary:  ["Let me put your day-by-day together — this'll take a moment.", "Let me build out your full trip now."],
  flight:     ["Let me check live flights for you.", "Let me pull up the best flights."],
  cab:        ["Let me find you a ride.", "Let me sort out your transfer."],
  restaurant: ["Let me find you some great tables.", "Let me pull up the best places to eat."],
  golf:       ["Let me check the tee times.", "Let me look at the courses for you."],
  activity:   ["Let me see what's on.", "Let me find the best things to do."],
}
const INTERIM_ORDER = ['itinerary', 'flight', 'cab', 'restaurant', 'golf', 'activity']
function interimLineFor(intents: string[], variant: number): string {
  const key = INTERIM_ORDER.find(k => intents.includes(k))
  if (!key) return ''
  const arr = INTERIM_LINES[key]
  return arr[variant % arr.length]
}


export default function SashaChat({ user, onSashaResponse, onListeningChange, onPhotos, initialMessage, emptyState, avatarSpeaking, onInterrupt, presetPrompts, onSetGate, avatarSpeechGetter, isRespondingRef, readyToListen, onThinking, onItinerary, language = 'en', registerSend, messages: propMessages, setMessages: propSetMessages, richItinerary = null, photos = [], activePhoto = 0, onSelectPhoto, onBook, onVoiceConnected, onMicError, onMicDevices, onBooked, onAwaitPayment, onBookItem, onItineraryId, bookingRef, activeTab = 'chat', onTabChange, unseenTabs = [], onMarkUnseen, onBuildingChange, ideasCache, onIdeasCache }: SashaChatProps) {
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
  const [hotels, setHotels] = useState<{ name: string; stars: number; price_from: number; blurb: string; city: string; book_url: string; rating?: number; reviews?: number; tag?: string; offer_id?: string; amount_usd?: number; nights?: number }[]>([])
  // Typed booking cards (flights, airport transfers, activities, restaurants) surfaced this
  // turn — real options from live web search. Hotel/flight/cab options carry a server-priced
  // `offer_id` (+ amount_usd) so they can be booked & paid through Stripe like the whole trip;
  // options without one (activities, restaurants, fallbacks) keep the external deep-link.
  const [bookings, setBookings] = useState<{ type: string; title: string; dest?: string; options: { name: string; detail?: string; price?: string; book_url: string; offer_id?: string; amount_usd?: number }[] }[]>([])
  // Photos Sasha surfaced, keyed by the index of the assistant message that produced them.
  const [photosByMsg, setPhotosByMsg] = useState<Record<number, Photo[]>>({})
  // Opening state: real Vietnam destinations, each with its own live photo. Before this the
  // panel was literally empty until the first reply landed — the removed "Right now" block had
  // been the only thing occupying it, and no emptyState was ever passed in.
  const [openers, setOpeners] = useState<{ location: string; blurb: string; url: string; thumb: string; photographer: string }[]>([])

  useEffect(() => {
    let cancelled = false
    fetch(apiUrl('/api/photos/destinations'), { headers: apiHeaders() })
      .then(r => r.json())
      .then(d => { if (!cancelled && d?.destinations?.length) setOpeners(d.destinations) })
      .catch(() => {})   // silent: the opener is decoration, never block the chat on it
    return () => { cancelled = true }
  }, [])
  // Single-flight guard: one conductor request at a time. Prevents duplicate STT
  // finals (or fast double-taps) from firing concurrent calls and stacking replies.
  const inFlightRef = useRef(false)

  // ── Itinerary build feedback ───────────────────────────────────────────────
  // Building a day-by-day plan takes 13-45s (see ITINERARY_TIMEOUT_S). For that whole window
  // Sasha said nothing and the UI showed nothing, so the guest sat in front of a dead screen
  // wondering if it had broken — and anything they said meanwhile was silently swallowed by
  // the in-flight lock. We can't learn the intent from the response (it only arrives at the
  // END), so predict it from the outgoing message using the same vocabulary the backend
  // classifies on, and from force_intent when the UI already knows.
  //
  // A wrong prediction is cheap and self-correcting: the guest lands on the Trip tab a moment
  // early and the banner clears when the turn ends either way. It never gates a real send —
  // it's presentation only.
  // Guards a late classify from re-opening the banner after its turn already ended.
  const turnSeqRef = useRef(0)
  // Rotates the interim-line variant so repeated searches in one session don't say the same words.
  const interimVariantRef = useRef(0)
  const [building, setBuilding] = useState(false)
  const [buildStep, setBuildStep] = useState(0)
  const BUILD_STEPS = [
    'Mapping out your route…',
    'Picking places to stay…',
    'Finding things worth doing…',
    'Checking prices and links…',
    'Putting the days in order…',
  ]
  useEffect(() => { onBuildingChange?.(building) }, [building])
  useEffect(() => {
    if (!building) { setBuildStep(0); return }
    // Walk the steps and hold on the last one — a build can outrun the list, and a stalled
    // ticker reads as "finishing up" rather than "frozen".
    const id = setInterval(() => setBuildStep(s => Math.min(s + 1, BUILD_STEPS.length - 1)), 4000)
    return () => clearInterval(id)
  }, [building])
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
    // Predicted itinerary build → take the guest to the Trip tab and show progress there, so
    // the long silent stretch has a visible owner instead of looking like a hang.
    stickToBottomRef.current = true   // a deliberate send always re-pins
    const turnId = ++turnSeqRef.current
    const showBuilding = () => { setBuilding(true); onTabChange?.('trip') }
    // One interim line per turn. `classifiedIntents` is filled by the parallel classify below (or
    // is the known intent for an idea-build). fireInterim voices the context line for a slow,
    // card-producing intent — but never a second line, and never if the answer already landed.
    let spokeInterim = false
    let classifiedIntents: string[] = opts?.intent ? [opts.intent] : []
    let interimTimer: any
    const fireInterim = () => {
      if (spokeInterim || turnSeqRef.current !== turnId || !inFlightRef.current) return
      const line = interimLineFor(classifiedIntents, interimVariantRef.current++)
      if (line) { spokeInterim = true; onThinking?.(line) }
    }
    if (opts?.intent === 'itinerary') {
      showBuilding()   // UI already knows — no round trip needed
      fireInterim()    // a build is always long (10-40s) — frame it immediately, don't wait
    } else {
      // Ask the backend what this turn will actually do, in PARALLEL with the real call so it
      // costs the turn nothing. ~8ms: pure keyword matching, no LLM, no agents. Doubles as the
      // source for the context-driven interim line.
      fetch(apiUrl('/api/agents/classify'), {
        method: 'POST',
        headers: apiHeaders(),
        body: JSON.stringify({
          message: content,
          conversation_history: historyBeforeMessage,
          session_id: chatSessionIdRef.current,
        }),
      })
        .then(r => r.json())
        .then(c => {
          // Only act if THIS turn is still running. A slow classify landing after its turn
          // finished would otherwise open a banner that nothing is left to close.
          if (turnSeqRef.current !== turnId || !inFlightRef.current) return
          classifiedIntents = c?.intents || []
          if (classifiedIntents.includes('itinerary')) showBuilding()
          // Speak the context line THE MOMENT we know the intent (~8ms), instead of waiting out
          // the 700ms fast-answer window. classify is the whole reason we know it's a slow,
          // card-producing turn — so there's no latency to trade off, and fireInterim self-guards
          // (no line for general chat, never a second line). This is the gap before "One moment…".
          fireInterim()
        })
        .catch(() => {})   // best-effort: never break a turn over a progress banner
      // Give a fast turn ~0.7s to simply answer; only frame a genuinely slow search with a
      // spoken line, so a quick reply isn't padded behind "let me check…".
      interimTimer = setTimeout(fireInterim, 700)
    }
    // Dead-silence safety net for a slow turn that produced no context line (general chat /
    // photos, or a classify that never resolved): after 5s, frame the wait once so she is never
    // silent. Skipped if a context line already fired. Both timers cleared when the answer lands.
    const thinkingTimer = setTimeout(() => {
      if (!spokeInterim && inFlightRef.current && turnSeqRef.current === turnId) {
        spokeInterim = true
        onThinking?.('One moment, let me get that for you.')
      }
    }, 5000)
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
      if (respPhotos?.length > 0) {
        onPhotos?.(respPhotos)
        // Pin these shots to the assistant turn that produced them so they read as part of the
        // conversation. Kept in a side map keyed by index rather than on the message itself,
        // because `conversation_history` is server-authoritative and only carries role/content
        // — anything attached to a message object is wiped on the next turn.
        const idx = conversation_history?.length > 0 ? conversation_history.length - 1 : null
        if (idx !== null) setPhotosByMsg(prev => ({ ...prev, [idx]: respPhotos }))
      }
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
      clearTimeout(interimTimer)
      setIsLoading(false)
      inFlightRef.current = false
      // Always clear the banner, on success, error, and timeout alike. A "building…" state
      // that outlives its turn is exactly the class of stuck-forever UI this app has been
      // bitten by before, so it is released in finally and nowhere else.
      setBuilding(false)
    }
  }

  // Expose the latest sendMessage to the parent (for budget/revise quick-actions).
  const sendRef = useRef(sendMessage)
  sendRef.current = sendMessage
  useEffect(() => { registerSend?.((t: string) => sendRef.current(t)) }, [])

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  // .lw-stream is overflow-y:auto but nothing ever scrolled it, so the conversation ran off
  // the bottom of the panel and every card Sasha surfaced (flights, stays, tours, the photo
  // hero) rendered BELOW the transcript, off-screen. That is why her replies lean on "they're
  // on the right" — the guest had to find the content by hand. Now the panel follows the
  // conversation and brings whatever she just surfaced into view.
  // Scroll to the thing that actually changed — NOT to the bottom of the panel. The stream is
  // laid out transcript → "Found for you" cards → "Right now" photos, and that photo panel is
  // persistent furniture that re-renders every turn. Scrolling to the end therefore parked the
  // guest on the photos every single time and pushed the live conversation off the top.
  const streamRef = useRef<HTMLDivElement | null>(null)
  const lastMsgRef = useRef<HTMLDivElement | null>(null)
  // Don't yank a guest who has deliberately scrolled up to re-read something.
  //
  // Deliberately keyed on user INTENT (wheel / touch), not on distance-from-bottom. Because we
  // anchor the newest message to the TOP, a turn that surfaces cards legitimately leaves plenty
  // of content below the fold — a distance-based check would read that as "the guest scrolled
  // away" and quietly disable auto-follow for the rest of the session after the very first
  // turn that showed a card.
  const stickToBottomRef = useRef(true)

  // "Scroll for more" cue. Because the newest message is pinned to the TOP (see below), a turn
  // that surfaces flights / stays / a day-by-day plan legitimately leaves those cards BELOW the
  // fold — and a guest who doesn't realise the panel scrolls never sees them (the exact demo
  // feedback). Show a gentle nudge whenever real content sits under the fold; hide it at the end.
  const [showScrollCue, setShowScrollCue] = useState(false)
  const recomputeScrollCue = () => {
    const el = streamRef.current
    if (!el) { setShowScrollCue(false); return }
    setShowScrollCue(el.scrollHeight - el.scrollTop - el.clientHeight > 56)
  }
  const jumpToBottom = () => {
    const el = streamRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    stickToBottomRef.current = true
    setShowScrollCue(false)
  }

  const onStreamWheel = (e: React.WheelEvent) => {
    if (e.deltaY < 0) {
      stickToBottomRef.current = false   // scrolled up = reading something; leave them alone
      return
    }
    const el = streamRef.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 140) {
      stickToBottomRef.current = true    // scrolled back down to the end = following again
    }
  }

  // rAF so we measure AFTER React has painted the new node, not against the old height.
  const scrollTo = (el: HTMLElement | null, block: ScrollLogicalPosition) => {
    if (!el) return
    requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block }))
  }

  // ONE anchor: the newest message, pinned to the TOP of the panel.
  //
  // Two anchors fought here and the guest lost. Scrolling the message to 'end' parked it at
  // the bottom of the view, which pushes any cards below it off-screen; then a second effect
  // scrolled the CARDS to 'start', but the cards are the last thing in the stream, so there is
  // nothing beneath them to scroll against and the browser just ran to the bottom — burying
  // the conversation above the fold.
  //
  // Anchoring the newest message to the top fixes both cases at once, because everything Sasha
  // surfaces on a turn renders directly BELOW her message: you read the reply, and the stays /
  // flights / tours sit right under it. With no cards, there's nothing to scroll against and
  // it simply settles at the bottom — which is the correct place to be anyway.
  useEffect(() => {
    if (stickToBottomRef.current) scrollTo(lastMsgRef.current, 'start')
  }, [messages, isLoading])

  // Re-measure the below-fold cue after a turn paints its cards. Keyed on the height-affecting
  // state (messages + the card collections), one rAF so we measure the new layout, not the old.
  useEffect(() => {
    const id = requestAnimationFrame(recomputeScrollCue)
    return () => cancelAnimationFrame(id)
  }, [messages, isLoading, bookings, hotels, richItinerary])

  // Cards re-pin (the guest asked for them) but do NOT get their own scroll target — they're
  // already in view under the message that announced them.
  useEffect(() => {
    if (!bookings.length && !hotels.length) return
    stickToBottomRef.current = true
    scrollTo(lastMsgRef.current, 'start')
  }, [bookings, hotels])
  // NOTE: `photos` deliberately does NOT trigger a scroll. It refreshes on almost every turn,
  // and it lives below the cards, so following it is exactly the bug above.

  // Prefer the party size the current plan was actually built for — a "make it 4" rebuild
  // carries the new count on the itinerary, so the trip view follows it instead of the static
  // profile field (which never changes mid-conversation and left the panel showing the old size).
  const travellerCount = richItinerary?.travellers ?? richItinerary?.cost_breakdown?.travellers ?? (user.travellers?.length || 2)
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

      {tab === 'trip' && building && (
        <div className="lw-building">
          <div className="lw-building-orb"><Loader2 className="w-5 h-5 animate-spin" /></div>
          <div className="lw-building-k">Building your itinerary</div>
          <div className="lw-building-step">{BUILD_STEPS[buildStep]}</div>
          <div className="lw-building-bar"><span /></div>
          <div className="lw-building-hint">This takes up to a minute — Sasha is holding on until it's ready.</div>
        </div>
      )}
      {tab === 'trip' && !building && (
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
      <div className="lw-streamwrap">
      <div className="lw-stream" ref={streamRef} onWheel={onStreamWheel} onScroll={recomputeScrollCue}>

        {/* ── Conversation transcript ── */}
        {messages.length > 0 && <div className="lw-when">Conversation</div>}
        {messages.length === 0 && (emptyState ?? (
          openers.length > 0 ? (
            <>
              <div className="lw-when">Where to?</div>
              <div className="lw-openers">
                {openers.map((o, i) => (
                  <button
                    key={i}
                    className="lw-opener"
                    // Tapping a place just talks to Sasha — same path as typing it, so the
                    // normal intent routing (and her photo/card surfacing) applies.
                    onClick={() => sendMessage(`Tell me about ${o.location}`)}
                    style={{ animationDelay: `${i * 60}ms` }}
                  >
                    <img src={o.url} alt={o.location} loading="lazy" />
                    <span className="lw-opener-grad" />
                    <span className="lw-opener-cap">
                      <span className="lw-opener-loc">{o.location}</span>
                      <span className="lw-opener-blurb">{o.blurb}</span>
                    </span>
                  </button>
                ))}
              </div>
            </>
          ) : null
        ))}
        {messages.map((msg, i) => (
          <div key={i} ref={i === messages.length - 1 ? lastMsgRef : undefined} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`} style={{ flex: '0 0 auto' }}>
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
              {/* Photos Sasha surfaced on THIS turn, captioned with the place they're of. */}
              {photosByMsg[i]?.length > 0 && (
                <div className="lw-msgshots">
                  <div className="lw-msgshots-loc">{photosByMsg[i][0]?.location || 'Vietnam'}</div>
                  <div className="lw-msgshots-row">
                    {photosByMsg[i].slice(0, 3).map((p, pi) => (
                      <a
                        key={pi}
                        className="lw-msgshot"
                        href={p.unsplash_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={p.description || p.location}
                      >
                        <img src={p.thumb || p.url} alt={p.location || p.description || 'Vietnam'} loading="lazy" />
                        <span className="lw-msgshot-by">📷 {p.photographer}</span>
                      </a>
                    ))}
                  </div>
                </div>
              )}
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
                        {o.offer_id && (o.amount_usd ?? 0) > 0 ? (
                          <div className="lw-actions">
                            <button className="price" onClick={() => onBookItem?.({ offer_id: o.offer_id!, label: `${b.title} · ${o.name}`, amount_usd: o.amount_usd!, kind: b.type, name: o.name })}>
                              Book &amp; Pay ${o.amount_usd!.toLocaleString()}
                            </button>
                            <a className="viewlink" href={o.book_url} target="_blank" rel="noopener noreferrer">View ↗</a>
                          </div>
                        ) : (
                          <a className="price" href={o.book_url} target="_blank" rel="noopener noreferrer">Book</a>
                        )}
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
                      {h.offer_id && (h.amount_usd ?? 0) > 0 ? (
                        <div className="lw-actions">
                          <button className="price" onClick={() => onBookItem?.({ offer_id: h.offer_id!, label: `${h.nights ?? 1} night${(h.nights ?? 1) !== 1 ? 's' : ''} · ${h.name}`, amount_usd: h.amount_usd!, kind: 'hotel', name: h.name })}>
                            Book &amp; Pay ${h.amount_usd!.toLocaleString()}
                          </button>
                          <a className="viewlink" href={h.book_url} target="_blank" rel="noopener noreferrer">View ↗</a>
                        </div>
                      ) : (
                        <a className="price" href={h.book_url} target="_blank" rel="noopener noreferrer">Book</a>
                      )}
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

        {/* The "Right now" photo panel used to live here. It was persistent furniture
            pinned BELOW the cards, captioned with the photo's Unsplash description (which
            is a photographer's free-text caption, so it read "Exploring 4:51pm"), and it
            re-rendered every turn. Photos now appear inline under the message that
            surfaced them, captioned with the actual place — see lw-msgshots above. The
            `photos`/`activePhoto`/`onSelectPhoto` props stay on the interface: the page
            still owns that state and uses it for the call-panel backdrop. ── */}
      </div>
      {showScrollCue && (
        <button className="lw-scrollcue" onClick={jumpToBottom} aria-label="Scroll down to see the full details">
          <span aria-hidden>↓</span> Scroll to see more
        </button>
      )}
      </div>
      )}

      {/* ── Composer ── */}
      <div className="lw-composer">
        <div className="field">
          <VoiceButton
            // HARD mute while the plan builds AND for the whole in-flight turn: barge-in can't
            // defeat it, because there is nothing to barge into (the turn is server-side). Gating
            // on `isLoading` too — not just `building` — closes the window where a voice-started
            // build's async classify hasn't flipped `building` yet: the mic is deaf for the entire
            // turn, so a stray utterance during creation can never post or badge Chat. inFlightRef
            // already dropped such sends; this makes "Not listening" literally true, not a label.
            muted={building || isLoading}
            // Speaking used to FORCE the guest back to Chat on every single transcript. That
            // fought them constantly: reading the plan on Trip and saying "make day 3 lighter"
            // threw them onto Chat, away from the very thing they were editing. Worse, during
            // an itinerary build the utterance was dropped by the in-flight lock anyway — so
            // they got yanked off the progress screen AND ignored.
            //
            // The page already had the right answer (`markUnseen`, "mark it with a dot instead
            // of yanking them off the conversation") — it just was never wired to the chat.
            // Now: never navigate on speech; if Chat is in the background, badge it.
            onTranscript={(text) => {
              if (building) {
                // She genuinely isn't listening while the plan builds — the lock would bin
                // this anyway, so drop it here rather than silently swallowing it downstream.
                console.log('[LOCK] transcript ignored — itinerary building')
                return
              }
              if (tab !== 'chat') onMarkUnseen?.('chat')
              sendMessage(text)
            }}
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
            onMicDevices={onMicDevices}
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
        .lw-streamwrap{position:relative;flex:1;min-height:0;display:flex;flex-direction:column}
        .lw-streamwrap>.lw-stream{flex:1}
        .lw-scrollcue{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);display:flex;align-items:center;gap:5px;padding:5px 13px;font-size:12px;line-height:1;color:rgba(255,255,255,.8);background:rgba(20,20,28,.82);backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,.12);border-radius:999px;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.35);z-index:5;animation:lwcuein .2s ease}
        .lw-scrollcue:hover{background:rgba(30,30,42,.94);color:#fff}
        @keyframes lwcuein{from{opacity:0;transform:translate(-50%,4px)}to{opacity:1;transform:translate(-50%,0)}}
        .lw-stream{flex:1;min-height:0;overflow-y:auto;padding:18px 18px 24px;display:flex;flex-direction:column;gap:13px}
        /* Itinerary build progress — owns the 13-45s window the plan takes to generate. */
        .lw-building{flex:1;min-height:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:32px 24px;text-align:center}
        .lw-building-orb{width:46px;height:46px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#DAA520;background:rgba(218,165,32,.1);border:1px solid rgba(218,165,32,.3)}
        .lw-building-k{font-size:15px;font-weight:650;color:#fff;margin-top:2px}
        .lw-building-step{font-size:12.5px;color:rgba(255,255,255,.6);min-height:18px}
        .lw-building-bar{width:190px;height:3px;border-radius:3px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:4px}
        /* Indeterminate on purpose: the backend reports no percentage, and a fake one that
           stalls at 90% is worse than an honest sweep. */
        .lw-building-bar span{display:block;height:100%;width:38%;border-radius:3px;background:linear-gradient(90deg,transparent,#DAA520,transparent);animation:lw-sweep 1.3s ease-in-out infinite}
        @keyframes lw-sweep{0%{transform:translateX(-100%)}100%{transform:translateX(363%)}}
        .lw-building-hint{font-size:11px;color:rgba(255,255,255,.34);margin-top:6px;max-width:280px;line-height:1.5}
        /* Opening destination gallery — fills the workspace before the first turn. */
        .lw-openers{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
        .lw-opener{position:relative;display:block;padding:0;border:1px solid rgba(255,255,255,.08);border-radius:14px;overflow:hidden;aspect-ratio:3/2;cursor:pointer;background:rgba(255,255,255,.04);text-align:left;opacity:0;animation:lw-op-in .45s ease forwards}
        @keyframes lw-op-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
        .lw-opener img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .5s ease}
        .lw-opener:hover img{transform:scale(1.07)}
        .lw-opener:hover{border-color:rgba(218,165,32,.55)}
        .lw-opener-grad{position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.85) 0%,rgba(0,0,0,.25) 45%,transparent 75%)}
        .lw-opener-cap{position:absolute;left:0;right:0;bottom:0;padding:10px 11px;display:flex;flex-direction:column;gap:2px}
        .lw-opener-loc{font-size:14px;font-weight:650;color:#fff;letter-spacing:.01em}
        .lw-opener-blurb{font-size:10.5px;color:rgba(255,255,255,.62);line-height:1.35}
        @media (max-width:760px){.lw-openers{grid-template-columns:repeat(2,1fr)}}
        /* Photos Sasha surfaces, inline under her message and captioned with the real place. */
        .lw-msgshots{margin-top:8px}
        .lw-msgshots-loc{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#DAA520;margin-bottom:6px}
        .lw-msgshots-row{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
        .lw-msgshot{position:relative;display:block;border-radius:10px;overflow:hidden;aspect-ratio:4/3;border:1px solid rgba(255,255,255,.08);text-decoration:none;background:rgba(255,255,255,.04)}
        .lw-msgshot img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .35s ease}
        .lw-msgshot:hover img{transform:scale(1.06)}
        /* Unsplash's API guidelines require visible photographer attribution. */
        .lw-msgshot-by{position:absolute;left:0;right:0;bottom:0;padding:8px 6px 4px;font-size:9px;color:rgba(255,255,255,.85);background:linear-gradient(to top,rgba(0,0,0,.75),transparent);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        @media (max-width:520px){.lw-msgshots-row{grid-template-columns:repeat(2,1fr)}}
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
        .lw-opt button.price{background:linear-gradient(135deg,#DAA520,#B8860B);color:#fff;border-color:transparent;cursor:pointer;font-family:inherit}
        .lw-opt button.price:hover{filter:brightness(1.08)}
        .lw-opt .lw-actions{display:flex;flex-direction:column;align-items:flex-end;gap:5px;flex-shrink:0}
        .lw-opt .viewlink{font-size:11px;color:rgba(255,255,255,.45);text-decoration:none;white-space:nowrap}
        .lw-opt .viewlink:hover{color:rgba(255,255,255,.7)}
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
