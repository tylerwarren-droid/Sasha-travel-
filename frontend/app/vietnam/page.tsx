'use client'

import { useState, useCallback, useEffect, useLayoutEffect, useRef } from 'react'
import { MicOff, MessageSquare, Sparkles, Map as MapIcon, User as UserIcon, Plus, Play, Mic, Send } from 'lucide-react'
import SashaAvatar, { prefetchAvatarSession } from '../components/SashaAvatar'
import SashaChat, { WorkspaceTab } from '../components/SashaChat'
import type { MicDevicesInfo } from '../components/VoiceButton'
import type { Idea } from '../components/workspace/IdeasPanel'
import type { RichItinerary } from '../components/ItineraryDays'
import VnFlag from '../components/VnFlag'
import LogoMark from '../components/portal/LogoMark'
import { stripMarkdown } from '@/lib/markdown'
import { apiUrl, apiHeaders } from '@/lib/api'
import { PAYMENTS_ENABLED, SAVED_CARD_LAST4 } from '@/lib/flags'
import { buildItineraryHtml, buildItineraryText } from '@/lib/itineraryDoc'
import { User, Itinerary } from '@/types'

const PRESET_PROMPTS = ['Plan a 7 day trip', 'Tell me about Hoi An', 'Best golf courses', 'Phu Quoc beaches']
// Sample plan for `?ui=preview` (layout QA of the Trip board without a backend). Illustrative
// numbers; the flag is never set in normal use.
const PREVIEW_PLAN: RichItinerary = {
  title: 'Hoi An & Da Nang · 7 days',
  summary: 'Lantern season in the old town, a cooking class in Tra Que, then Da Nang beaches and the Golden Bridge.',
  estimated_total_usd: 4860,
  travellers: 2,
  cost_breakdown: { hotels: 1890, experiences: 1240, meals: 860, transport: 870, travellers: 2 },
  days: [
    { day: 1, city: 'Hoi An', title: 'Arrive Da Nang, evening in Hoi An', description: 'Private transfer from the airport, check in by the river, first lantern walk.', image: 'https://images.unsplash.com/photo-1691927644490-e1a24b366a5e?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=900', hotel: { name: 'Anantara Hoi An Resort', book_url: '', rating: 9.1, reviews: 2140, tag: 'Riverside' }, activities: [{ time: '18:00', name: 'Lantern walk along the Thu Bon', blurb: 'The old town lights up at dusk.', book_url: '' }] },
    { day: 2, city: 'Hoi An', title: 'Old town walk, cooking class', description: '', image: null, hotel: null, activities: [{ time: '09:00', name: 'Heritage walk with a local guide', blurb: '', book_url: '' }, { time: '15:00', name: 'Tra Que village cooking class', blurb: '', book_url: '' }] },
    { day: 3, city: 'Hoi An', title: 'My Son sanctuary at sunrise', description: '', image: null, hotel: null, activities: [] },
    { day: 4, city: 'Da Nang', title: 'Ba Na Hills & Golden Bridge', description: '', image: null, hotel: { name: 'InterContinental Danang Sun Peninsula', book_url: '', rating: 9.4, reviews: 3280 }, activities: [] },
    { day: 5, city: 'Da Nang', title: 'My Khe beach, seafood by the sea', description: '', image: null, hotel: null, activities: [] },
    { day: 6, city: 'Da Nang', title: 'Son Tra peninsula & Linh Ung pagoda', description: '', image: null, hotel: null, activities: [] },
    { day: 7, city: 'Da Nang', title: 'Slow morning, fly home', description: '', image: null, hotel: null, activities: [] },
  ],
}
// Welcome-screen destination gallery (approved design, board 1). Same curated Unsplash set the
// backend's foto_agent falls back to, so the imagery matches what Sasha later surfaces. The three
// unnamed shots are captioned by theme rather than guessed at as places.
const WELCOME_OPENERS: { location: string; blurb: string; ask: string; url: string }[] = [
  { location: 'Ha Long Bay', blurb: 'Limestone karsts, overnight junks', ask: 'Tell me about Ha Long Bay', url: 'https://images.unsplash.com/photo-1528127269322-539801943592?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=600' },
  { location: 'Hoi An', blurb: 'Lantern-lit old town', ask: 'Tell me about Hoi An', url: 'https://images.unsplash.com/photo-1691927644490-e1a24b366a5e?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=600' },
  { location: 'Mu Cang Chai', blurb: 'Rice terraces in gold', ask: 'Tell me about Mu Cang Chai', url: 'https://images.unsplash.com/photo-1609412058473-c199497c3c5d?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=600' },
  { location: 'Island hopping', blurb: 'Boats, coves and slow days', ask: 'Where should we go island hopping in Vietnam?', url: 'https://images.unsplash.com/photo-1528127269322-539801943592?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=600&h=400' },
  { location: 'River valleys', blurb: 'Water between the peaks', ask: 'Show me Vietnam\'s river valleys', url: 'https://images.unsplash.com/photo-1609412058473-c199497c3c5d?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=600&h=400' },
  { location: 'Beach days', blurb: 'White sand, warm sea', ask: 'Which Vietnam beaches would you pick?', url: 'https://images.unsplash.com/photo-1691927644490-e1a24b366a5e?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=600&h=400' },
]

const DEMO_USER: User = {
  display_name: 'Jon Peters',
  email: 'jon@kanoe.ai',
  default_currency: 'USD',
  sasha_context: 'Jon loves cultural immersion, authentic food experiences, and luxury travel across Asia.',
  travellers: [
    { relation: 'self', first_name: 'Jon' },
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

// Browsers pad device labels with boilerplate ("Default - MacBook Air Microphone (Built-in)")
// that eats the pill's width without telling the guest anything. Trim it to the part that
// actually distinguishes one mic from another.
function micLabel(label: string, i: number): string {
  const trimmed = (label || '')
    .replace(/^Default\s*[-–]\s*/i, '')
    .replace(/\s*\((Built-in|Virtual)\)\s*$/i, '')
    .trim()
  return trimmed || `Microphone ${i + 1}`
}

const INITIAL_ITINERARY: Itinerary = {
  title: 'Vietnam Discovery',
  ota_channel: 'culture',
  status: 'draft',
  total_fiat: 0,
  items: []
}

interface Photo {
  url: string
  thumb: string
  description: string
  photographer: string
  location?: string   // the place the shot is of (backend caption), used for tile labels
}

export default function VietnamPage() {
  const [speakFn, setSpeakFn] = useState<((text: string) => void) | null>(null)
  const speakFnRef = useRef<((text: string) => void) | null>(null)
  const interruptFnRef = useRef<(() => void) | null>(null)
  const gateRef = useRef<((value: boolean) => void) | null>(null)
  const handleSetGate = useCallback((fn: (value: boolean) => void) => { gateRef.current = fn }, [])
  const handleGate = useCallback((value: boolean) => { gateRef.current?.(value) }, [])

  // ── Deliberate mute while the itinerary builds ─────────────────────────────
  // The gate lives here, next to the avatar's own speak-driven gating, so there is exactly
  // ONE owner and the two can't fight. Closing it drops mic frames before Deepgram ever sees
  // them, so "Not listening" is literally true rather than a label over a live mic.
  //
  // The existing lockWatchdog can't cover this: it only arms when Sasha SPEAKS, and she is
  // silent for the whole build. So this carries its own backstop — a closed gate that never
  // reopens is the freeze this app already shipped once, and it must not be reachable.
  const [micMuted, setMicMuted] = useState(false)
  const buildWatchdogRef = useRef<any>(null)
  const handleBuildingChange = useCallback((isBuilding: boolean) => {
    clearTimeout(buildWatchdogRef.current)
    setMicMuted(isBuilding)
    // Closing is always safe; RE-OPENING is not — if Sasha is already speaking the itinerary
    // summary, force-opening here put the live mic under her own voice for the whole read
    // (SashaAvatar's speak-started guard can't re-close: speakingRef is already true). Let
    // the avatar's openGate() release the mic when the utterance actually ends.
    if (isBuilding || !isRespondingRef.current) handleGate(isBuilding)
    if (isBuilding) {
      // Outlives the backend's 45s itinerary ceiling. If the turn dies without ever clearing
      // `building`, the mic comes back anyway.
      buildWatchdogRef.current = setTimeout(() => {
        console.warn('[GATE] build watchdog force-reopened the mic')
        setMicMuted(false)
        handleGate(false)
      }, 60000)
    }
  }, [handleGate])
  useEffect(() => () => clearTimeout(buildWatchdogRef.current), [])
  const [isListening, setIsListening] = useState(false)
  const [chatMessages, setChatMessages] = useState<any[]>([])
  const [paymentModal, setPaymentModal] = useState<'card' | 'crypto' | null>(null)
  // A single hotel/flight/cab the guest tapped "Book & Pay" on. When set, the payment modal
  // and checkout run against this offer (server-priced by offer_id) instead of the whole trip.
  const [pendingOffer, setPendingOffer] = useState<{ offer_id: string; label: string; amount_usd: number; kind: string; name: string } | null>(null)
  // A confirmed single-item booking (from the Stripe return leg), shown as its own confirmation.
  const [itemBooked, setItemBooked] = useState<{ ref?: string; label?: string; amount?: number; kind?: string; emailSent?: boolean; paidWith?: { last4: string } | null } | null>(null)
  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  // Typed booking details — names/emails are unreliable over voice STT, so collect them here.
  const [payerName, setPayerName] = useState('')
  const [payerEmail, setPayerEmail] = useState('')
  const [payResult, setPayResult] = useState<'paid' | 'canceled' | null>(null)
  // True while the backend is confirming a Stripe payment on the return leg.
  const [verifying, setVerifying] = useState(false)
  // The stored trip a payment applies to. The server prices checkout from this id — the
  // browser no longer states the amount.
  const [itineraryId, setItineraryId] = useState<string | null>(null)
  // Ref mirror: one conductor turn can deliver itinerary_id AND action=await_payment
  // together, and SashaChat fires onItineraryId then onAwaitPayment synchronously — state
  // hasn't flushed yet, so reserveTrip must read the ref, never the state.
  const itineraryIdRef = useRef<string | null>(null)
  const handleItineraryId = useCallback((id: string) => {
    itineraryIdRef.current = id
    setItineraryId(id)
  }, [])
  // The booking parked on Sasha's "saved card ending 1003, or a different card?" question
  // (action confirm_card). `item` is the single offer; null means the whole stored trip. The
  // backend is stateless across turns, so the browser is what remembers WHAT is being booked;
  // the next turn only says HOW (pay_saved_card / pay_new_card). A ref, not state: the answer
  // can land on the very next render.
  const pendingCardRef = useRef<{ item: { offer_id: string; label: string; amount_usd: number; kind: string; name: string } | null; savedCard: { last4: string } | null } | null>(null)

  // ── Deliberate mute while a payment modal is open ─────────────────────────
  // The guest is typing their name/email into the Complete Booking form; a hot mic
  // behind the modal keeps feeding Deepgram and leaves a "Listening…" equaliser lit
  // over a dialog nobody is talking to. Reuse the SAME single-owner gate the build-mute
  // uses so the two can't fight — closing it drops frames before Deepgram sees them, so
  // the pill reads "Not listening" truthfully. Payment always follows a completed build,
  // so this never overlaps handleBuildingChange in practice.
  useEffect(() => {
    const modalOpen = paymentModal !== null
    setMicMuted(modalOpen)
    if (modalOpen || !isRespondingRef.current) handleGate(modalOpen)
  }, [paymentModal, handleGate])

  const [photos, setPhotos] = useState<Photo[]>([])
  const [activePhoto, setActivePhoto] = useState(0)
  const [engaged, setEngaged] = useState(false)
  // Which workspace tab is showing. Chat is the default: this is a voice call, so the
  // transcript is what the guest follows. When Sasha updates a tab they aren't looking at,
  // we mark it with a dot (see `unseenTabs`) instead of yanking them off the conversation.
  const [rightTab, setRightTab] = useState<WorkspaceTab>('chat')
  const [unseenTabs, setUnseenTabs] = useState<WorkspaceTab[]>([])
  const markUnseen = useCallback((tab: WorkspaceTab) => {
    setRightTab(cur => { if (cur !== tab) setUnseenTabs(u => (u.includes(tab) ? u : [...u, tab])); return cur })
  }, [])
  const handleTabChange = useCallback((tab: WorkspaceTab) => {
    setRightTab(tab)
    setUnseenTabs(u => u.filter(t => t !== tab))
  }, [])
  const [started, setStarted] = useState(false)
  const [richItinerary, setRichItinerary] = useState<RichItinerary | null>(null)
  // Ideas held at page level so they survive IdeasPanel unmounting on every tab switch.
  const [ideasCache, setIdeasCache] = useState<Idea[] | null>(null)
  const [language, setLanguage] = useState('en')
  const sendChatRef = useRef<((t: string) => void) | null>(null)
  const registerSend = useCallback((fn: (t: string) => void) => { sendChatRef.current = fn }, [])
  const handleRevise = useCallback((text: string) => { sendChatRef.current?.(text) }, [])
  const photoInterval = useRef<any>(null)
  const lastRepeatTextRef = useRef<string>('')
  // A live, timestamped record of what the avatar has ACTUALLY said, supplied by SashaAvatar
  // from its transcription events. Better than `lastRepeatTextRef` (the last text we ASKED
  // for) because it also covers utterances we didn't request — notably the opening greeting,
  // which the echo filter could never match before.
  const avatarSaidRef = useRef<(() => string) | null>(null)
  const handleAvatarSpeechBuffer = useCallback((getText: () => string) => { avatarSaidRef.current = getText }, [])
  const isRespondingRef = useRef(false)
  const lockWatchdogRef = useRef<any>(null)
  // A real answer that arrived while Sasha was still speaking an interim ("let me check…") line.
  // Held here and voiced the moment her current sentence ends, so she is never cut off and the
  // result is only spoken once her existing communication is over.
  const pendingSpeechRef = useRef<string | null>(null)
  const [voiceReady, setVoiceReady] = useState(false)
  const [voiceConnected, setVoiceConnected] = useState(false)
  // A mic/voice failure, shown ON THE CALL PANEL. Previously the panel's only non-live state
  // was "Starting microphone…", which it showed forever when permission was denied — so a
  // blocked mic (common on a fresh demo machine) looked identical to a slow one, and the
  // actual reason sat unnoticed in the composer on the far side of the screen.
  const [micError, setMicError] = useState<string | null>(null)
  // Mic picker, published up from VoiceButton so it can live as a pill next to the camera
  // toggle with the other call controls. Null until a real second input exists.
  const [micDevices, setMicDevices] = useState<MicDevicesInfo | null>(null)
  const [isAvatarSpeaking, setIsAvatarSpeaking] = useState(false)
  // A language switch remounts SashaAvatar (key={language}); if she was mid-utterance the
  // unmount clears her timers, so openGate/onSashaFinished never fire. Reset the page-side
  // lock immediately or the mic stays dead ("Sasha is speaking") until the 39s watchdog.
  useEffect(() => {
    isRespondingRef.current = false
    clearTimeout(lockWatchdogRef.current)
    setIsAvatarSpeaking(false)
    pendingSpeechRef.current = null
  }, [language])
  // Final booking state — set when the customer confirms the trip. Locks the itinerary into
  // a shareable / printable confirmation and ends the live session once Sasha finishes.
  const [booked, setBooked] = useState<{ ref?: string; emailSent?: boolean; paidWith?: { last4: string } | null } | null>(null)
  const [shareToast, setShareToast] = useState<string | null>(null)
  const endOnFinishRef = useRef(false)
  const bookEndTimerRef = useRef<any>(null)

  // Video-call chrome state (mockup UI): live caption, session timer, and user-camera PiP.
  const [caption, setCaption] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [camOn, setCamOn] = useState(false)
  // The guest's explicit choice, separate from `camOn` (which reports whether a stream is
  // actually live). Turning the camera off must STOP the tracks, not just hide the video —
  // otherwise the camera light stays on and the guest rightly assumes they're still filmed.
  const [camEnabled, setCamEnabled] = useState(true)
  const userVideoRef = useRef<HTMLVideoElement | null>(null)
  const camStreamRef = useRef<MediaStream | null>(null)

  // Warm the backend LLM path on page load so the FIRST spoken turn isn't cold. Fires
  // during the splash screen, overlapping the avatar cold-start — best-effort, ignored
  // on failure.
  useEffect(() => {
    fetch(apiUrl('/api/agents/warmup')).catch(() => {})
  }, [])

  // Warm the avatar session start while the guest is still reading the splash screen. The
  // token round-trip and the SDK chunk download used to happen only AFTER the tap, in series,
  // stacked on top of HeyGen's ~4s allocation — so the guest paid for all of it at once while
  // watching a loading screen. Minting a token doesn't start (or bill) a session. Re-runs on a
  // language change so the warmed token matches the token the avatar will actually ask for.
  useEffect(() => {
    if (started) return   // already running — nothing to warm
    const href = `/api/heygen/token?lang=${language}`
    prefetchAvatarSession(href)
    // Keep it warm. A token is only trusted for 60s (see PREFETCH_TTL_MS) — beyond that we
    // re-mint rather than risk starting with an expired one. Without this, a guest who reads
    // the splash for a minute would fall back to paying the full mint cost on the tap, which
    // is exactly the case we're trying to fix.
    const id = setInterval(() => prefetchAvatarSession(href), 45000)
    return () => clearInterval(id)
  }, [language, started])

  // Initial background photos — updated per-turn by conductor via onPhotos
  useEffect(() => {
    fetch(apiUrl('/api/photos/search'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'Vietnam landscape travel', count: 4 })
    })
      .then(r => r.json())
      .then(data => { if (data.photos?.length > 0) { setPhotos(data.photos); setActivePhoto(0) } })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (photos.length <= 1) return
    clearInterval(photoInterval.current)
    photoInterval.current = setInterval(() => {
      setActivePhoto(prev => (prev + 1) % photos.length)
    }, 5000)
    return () => clearInterval(photoInterval.current)
  }, [photos])

  // Live session timer for the call status bar — ticks while a session is active.
  useEffect(() => {
    if (!started) { setElapsed(0); return }
    setElapsed(0)
    const id = setInterval(() => setElapsed(e => e + 1), 1000)
    return () => clearInterval(id)
  }, [started])

  // User-camera picture-in-picture. Best-effort: show the live camera feed when the user
  // grants permission, otherwise fall back to the camera-off placeholder. Tracks are
  // always stopped on teardown so the camera light goes off when the session ends.
  useEffect(() => {
    if (!started || !camEnabled) return
    let cancelled = false
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: 'user' } })
      .then(stream => {
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return }
        camStreamRef.current = stream
        if (userVideoRef.current) userVideoRef.current.srcObject = stream
        setCamOn(true)
      })
      .catch(() => { if (!cancelled) setCamOn(false) })
    return () => {
      cancelled = true
      camStreamRef.current?.getTracks().forEach(t => t.stop())
      camStreamRef.current = null
      if (userVideoRef.current) userVideoRef.current.srcObject = null
      setCamOn(false)
    }
  }, [started, camEnabled])

  // Auto-start safety net: the voice loop connects once `voiceReady` is true, which is
  // normally flipped by the avatar's onReadyToListen. If that event is missed (avatar
  // cold-start, dropped event), the mic would never auto-connect and the user would have
  // to click it. This backstop flips it on a few seconds after the session starts so the
  // mic always comes up on its own. The mic stays gated until the avatar finishes greeting,
  // so connecting early is safe.
  useEffect(() => {
    if (!started) { setVoiceReady(false); setVoiceConnected(false); return }
    const t = setTimeout(() => setVoiceReady(true), 3500)
    return () => clearTimeout(t)
  }, [started])

  const fmtTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

  const handleAvatarReady = useCallback((speak: (text: string) => void, interrupt: () => void) => {
    setSpeakFn(() => speak)
    speakFnRef.current = speak
    interruptFnRef.current = interrupt
  }, [])

  const handleInterrupt = useCallback(() => {
    interruptFnRef.current?.()
  }, [])

  const handleEndSession = useCallback(() => {
    // Flipping `started` off unmounts SashaAvatar (-> avatar.stop() ends the LiveAvatar
    // session, stopping billing) and SashaChat (-> VoiceButton unmounts -> Deepgram WS
    // closes). Tap-to-start spins up a fresh session; chat history is preserved.
    interruptFnRef.current?.()
    isRespondingRef.current = false
    clearTimeout(lockWatchdogRef.current)
    clearTimeout(bookEndTimerRef.current)
    endOnFinishRef.current = false
    setIsAvatarSpeaking(false)
    speakFnRef.current = null
    interruptFnRef.current = null
    // Explicitly stop the camera here too — don't rely solely on the effect cleanup, so the
    // camera light goes off the moment the session ends (this is what "is the session over?"
    // checks visually).
    try { camStreamRef.current?.getTracks().forEach(t => t.stop()) } catch {}
    camStreamRef.current = null
    if (userVideoRef.current) userVideoRef.current.srcObject = null
    setCamOn(false)
    setEngaged(false)
    setStarted(false)
  }, [])

  // Handle Stripe Checkout's redirect back (success_url / cancel_url). On success we restore
  // the trip stashed before redirect and show the full "Trip booked!" confirmation, so paying
  // by card lands on the same rich confirmation as the voice "book it" path (no more bare toast).
  // Returning from Stripe. The ONLY thing the browser is trusted with here is the session id;
  // the backend asks Stripe whether it was actually paid, mints the reference, and hands back
  // the stored trip. Previously this trusted a bare `?paid=1` plus whatever sat in
  // sessionStorage — so typing the URL produced a confirmed booking, and cancelling then
  // revisiting it did too (the cancel path never cleared the stash).
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    const sessionId = p.get('session_id')
    const clearUrl = () => window.history.replaceState({}, '', '/vietnam')
    try { sessionStorage.removeItem('sasha_pending_trip') } catch {}

    if (p.get('canceled')) { setPayResult('canceled'); clearUrl(); return }
    if (!p.get('paid')) return

    if (!sessionId) {
      // `?paid=1` with no Stripe session — not a real return leg.
      setCheckoutError('We could not confirm that payment. If you were charged, contact support with your email address.')
      clearUrl()
      return
    }

    setVerifying(true)
    fetch(apiUrl(`/api/payments/verify?session_id=${encodeURIComponent(sessionId)}`), { headers: apiHeaders() })
      .then(r => r.ok ? r.json() : Promise.reject(new Error(String(r.status))))
      .then(data => {
        if (data?.paid && data?.booking_ref) {
          if (data.item) {
            // A single hotel/flight/cab was paid for — show the item confirmation, not the trip one.
            setItemBooked({ ref: data.booking_ref, label: data.item.label, amount: data.item.amount_usd, kind: data.item.kind, emailSent: Boolean(data.email_sent), paidWith: { last4: '' } })
          } else {
            if (data.itinerary?.days?.length) setRichItinerary(data.itinerary)
            else setPayResult('paid')   // no stored trip payload — at least confirm via toast
            setBooked({ ref: data.booking_ref, emailSent: Boolean(data.email_sent), paidWith: { last4: '' } })
            setRightTab('trip')
          }
        } else {
          setPayResult('canceled')  // Stripe says it isn't paid — don't claim otherwise.
        }
      })
      .catch(() => setCheckoutError('We could not reach the payment service to confirm your booking. Nothing has been lost — contact support and we will confirm it for you.'))
      .finally(() => { setVerifying(false); clearUrl() })
  }, [])

  // Stripe Checkout: create a hosted session on the backend and redirect to it. Card data
  // never touches our servers. A 501 means the demo's Stripe keys aren't set — surface it
  // calmly instead of crashing.
  // Reservation-only toast for a failed reserve call — rendered top-center like payResult.
  const [reserveError, setReserveError] = useState<string | null>(null)

  // Reservation-only path (payments disabled): Sasha simply takes the reservation. The
  // backend mints the reference instantly — no Stripe, no name/email form, so a verbal
  // "book it" completes end-to-end without a single tap.
  // `paidWith` = the saved card the guest chose when Sasha asked; the backend records it and
  // the confirmation says "booked" and names the card instead of a bare reservation.
  const reserveItem = useCallback(async (offer: { offer_id: string; label: string; amount_usd: number; kind: string; name: string }, paidWith?: { last4: string } | null) => {
    setReserveError(null)
    try {
      const res = await fetch(apiUrl('/api/payments/reserve'), {
        method: 'POST',
        headers: apiHeaders(),
        body: JSON.stringify({
          offer_id: offer.offer_id,
          ...(paidWith ? { payment_method: 'saved_card', card_last4: paidWith.last4 } : {}),
        }),
      })
      if (!res.ok) throw new Error(String(res.status))
      const data = await res.json()
      setItemBooked({ ref: data.booking_ref, label: offer.label, amount: offer.amount_usd, kind: offer.kind, paidWith: paidWith ?? null })
    } catch {
      setReserveError('Could not complete that reservation — please try again.')
      setTimeout(() => setReserveError(null), 4000)
    }
  }, [])

  const startCardCheckout = useCallback(async () => {
    setCheckoutError(null)
    // Two server-priced paths: a single card (offer_id) or the whole trip (itinerary_id).
    // Either way the server sets the price; the browser never supplies an amount.
    const isItem = !!pendingOffer
    const description = isItem ? pendingOffer!.label : (richItinerary?.title || 'Sasha Travel booking')
    if (!isItem && !itineraryId) {
      setCheckoutError('Build an itinerary first, then you can book it.')
      return
    }
    setCheckoutLoading(true)
    let navigated = false
    try {
      const res = await fetch(apiUrl('/api/payments/create-checkout'), {
        method: 'POST',
        headers: apiHeaders(),
        body: JSON.stringify({
          ...(isItem ? { offer_id: pendingOffer!.offer_id } : { itinerary_id: itineraryId }),
          currency: 'usd',
          description: payerName ? `${description} — ${payerName}` : description,
          customer_email: payerEmail || undefined,
        }),
      })
      if (res.status === 501) { setCheckoutError('Payments are not configured for this demo yet.'); return }
      if (!res.ok) { setCheckoutError('Could not start checkout. Please try again.'); return }
      const data = await res.json()
      if (data?.url) {
        // No need to stash the trip: Stripe reloads the page and the return handler fetches
        // the confirmed booking (and its itinerary) back from the server by session id.
        //
        // Navigate the TOP window, not this one: on /demo this page runs inside DemoPortal's
        // iframe, and checkout.stripe.com refuses to render in a frame (its CSP blocks
        // framing) — the guest saw Stripe's loading skeleton dead inside the portal. The
        // iframe is same-origin and unsandboxed, so redirecting `window.top` is permitted;
        // the try/catch keeps a plain non-embedded /vietnam working unchanged.
        try {
          (window.top ?? window).location.href = data.url
        } catch {
          window.location.href = data.url
        }
        // Deliberately KEEP checkoutLoading=true: navigation is in flight, and re-enabling
        // the button here let a fast double-click create a second Stripe session (finally
        // runs even on return, so this needs the flag below).
        navigated = true
        return
      }
      setCheckoutError('Could not start checkout. Please try again.')
    } catch {
      setCheckoutError('Could not reach the payment service.')
    } finally {
      if (!navigated) setCheckoutLoading(false)
    }
  }, [richItinerary, itineraryId, payerName, payerEmail, pendingOffer])

  // Start a FRESH session. chatMessages is page-level state that survives the avatar
  // restart, so without clearing it a new "Tap to start" shows the previous conversation
  // (and would resend that stale history to the conductor). Reset the conversation state
  // here so every new session begins clean.
  const handleStart = useCallback(() => {
    // Ask for the mic NOW — this click is a user gesture, so the permission prompt appears
    // immediately and is granted before the avatar finishes greeting. Otherwise the prompt
    // only pops up when the voice loop connects (mid-conversation) and voice silently fails.
    try {
      navigator.mediaDevices?.getUserMedia({ audio: true })
        .then(s => s.getTracks().forEach(t => t.stop()))
        .catch(() => {})
    } catch {}
    setChatMessages([])
    setEngaged(false)
    setVoiceReady(false)
    setRichItinerary(null)
    setBooked(null)
    // A new session starts on Chat with a clean slate. Without these, "Tap to start" could
    // open on the Trip tab from the last session — now showing an empty panel — or leave a
    // dot pointing at content that was just wiped.
    setRightTab('chat')
    setUnseenTabs([])
    setMicError(null)   // a fresh session re-asks for the mic; don't carry the old failure over
    setItineraryId(null)
    itineraryIdRef.current = null
    setIdeasCache(null)
    setPayResult(null)
    setCheckoutError(null)
    endOnFinishRef.current = false
    clearTimeout(bookEndTimerRef.current)
    setCaption('')
    isRespondingRef.current = false
    clearTimeout(lockWatchdogRef.current)
    setStarted(true)
  }, [])

  // Sasha produced a full day-by-day itinerary — SHOW it. She says out loud "your plan is
  // live on the right", so the plan has to be on the right: a subtle dot on a background tab
  // made her a liar and left guests staring at the chat wondering where the trip went.
  const handleItinerary = useCallback((itin: RichItinerary) => {
    setRichItinerary(itin)
    handleTabChange('trip')
  }, [handleTabChange])

  // (handleAwaitPayment lives below, after handleBooked — the reservation-only path needs
  // handleBooked and const declarations aren't hoisted.)

  const handlePhotos = useCallback((newPhotos: any[]) => {
    if (newPhotos?.length > 0) {
      setPhotos(newPhotos)
      setActivePhoto(0)
    }
  }, [])

  // The single place that actually drives the avatar to speak + arms the release watchdog.
  // Shared by the real answer, the interim "working on it" line, and the queued-answer flush,
  // so all three take the lock and the backstop timer identically.
  const speakNow = useCallback((spoken: string) => {
    if (!spoken || !speakFnRef.current) return
    lastRepeatTextRef.current = spoken
    setCaption(spoken)
    isRespondingRef.current = true
    console.log('[LOCK] acquired — Sasha speaking')
    speakFnRef.current(spoken)
    setEngaged(true)
    clearTimeout(lockWatchdogRef.current)
    const watchdogMs = Math.min(35000, Math.max(10000, spoken.length * 90)) + 4000
    lockWatchdogRef.current = setTimeout(() => {
      if (isRespondingRef.current) {
        console.warn('[LOCK] watchdog force-release after', watchdogMs, 'ms')
        isRespondingRef.current = false
        setIsAvatarSpeaking(false)
        gateRef.current?.(false)
        // A stuck utterance must not strand a queued answer behind it forever — drop it (the
        // answer text is already on screen in the transcript).
        pendingSpeechRef.current = null
      }
    }, watchdogMs)
  }, [])

  const handleSashaFinished = useCallback(() => {
    // A real answer was queued behind an interim line — voice it now instead of releasing, so
    // she flows straight from "let me check…" into the result with no gap and no cut-off.
    if (pendingSpeechRef.current) {
      const next = pendingSpeechRef.current
      pendingSpeechRef.current = null
      console.log('[LOCK] flushing queued answer after interim')
      speakNow(next)
      return
    }
    isRespondingRef.current = false
    clearTimeout(lockWatchdogRef.current)
    console.log('[LOCK] released — Sasha finished speaking')
    // After Sasha speaks the booking confirmation, end the live session (stops billing).
    if (endOnFinishRef.current) {
      endOnFinishRef.current = false
      handleEndSession()
    }
  }, [handleEndSession, speakNow])

  // Customer confirmed the trip — lock the final itinerary into a shareable confirmation and
  // end the session once the confirmation is spoken.
  const handleBooked = useCallback((ref?: string, paidWith?: { last4: string } | null) => {
    setBooked({ ref, paidWith: paidWith ?? null })
    // Turn the camera off immediately on booking — the call is effectively over, and this is
    // what the user looks at to confirm "the session ended". The avatar finishes its spoken
    // confirmation, then the live session is fully torn down (below).
    try { camStreamRef.current?.getTracks().forEach(t => t.stop()) } catch {}
    camStreamRef.current = null
    if (userVideoRef.current) userVideoRef.current.srcObject = null
    setCamOn(false)
    setIsListening(false)
    // End the avatar/voice session once the confirmation is spoken (handleSashaFinished), with
    // a bounded fallback so a missed speak-finished event can never leave the session running.
    endOnFinishRef.current = true
    clearTimeout(bookEndTimerRef.current)
    bookEndTimerRef.current = setTimeout(() => {
      if (endOnFinishRef.current) { endOnFinishRef.current = false; handleEndSession() }
    }, 14000)
  }, [handleEndSession])

  // Reserve the WHOLE stored trip (payments disabled). Uses handleBooked so the confirmation
  // modal shows and the live session winds down once Sasha finishes speaking, exactly like
  // the old paid path did after Stripe verified.
  const reserveTrip = useCallback(async (paidWith?: { last4: string } | null) => {
    setReserveError(null)
    const tripId = itineraryIdRef.current
    if (!tripId) {
      setReserveError('Build an itinerary first, then Sasha can book it.')
      setTimeout(() => setReserveError(null), 4000)
      return
    }
    try {
      const res = await fetch(apiUrl('/api/payments/reserve'), {
        method: 'POST',
        headers: apiHeaders(),
        body: JSON.stringify({
          itinerary_id: tripId,
          ...(paidWith ? { payment_method: 'saved_card', card_last4: paidWith.last4 } : {}),
        }),
      })
      if (!res.ok) throw new Error(String(res.status))
      const data = await res.json()
      const hasDays = Boolean(data.itinerary?.days?.length)
      if (hasDays) setRichItinerary(data.itinerary)
      if (hasDays || richItinerary) {
        handleTabChange('trip')
        handleBooked(data.booking_ref, paidWith)
      } else {
        // No trip payload to render the full confirmation with — the booked modal requires
        // richItinerary, so calling handleBooked here would end the session behind a modal
        // that never appears (dead page until reload). Show the compact confirmation instead.
        setItemBooked({ ref: data.booking_ref, label: 'Your Vietnam trip', amount: data.amount_usd, paidWith: paidWith ?? null })
      }
    } catch {
      setReserveError('Could not complete the reservation — please try again.')
      setTimeout(() => setReserveError(null), 4000)
    }
  }, [richItinerary, handleTabChange, handleBooked])

  // The guest asked to book the whole trip. Payments off → Sasha reserves it on the spot
  // (verbal "book the trip" completes hands-free). Payments on → legacy behavior: show the
  // itinerary and open the Stripe payment modal on the Trip tab.
  const handleAwaitPayment = useCallback(() => {
    if (!PAYMENTS_ENABLED) { reserveTrip(); return }
    setPendingOffer(null)   // whole-trip checkout — never inherit a previously tapped card
    handleTabChange('trip')
    setPaymentModal('card')
  }, [handleTabChange, reserveTrip])

  // ── Saved-card step (client ask 2026-09-05) ─────────────────────────────────────────
  // Turn 1: the guest said "book it" and Sasha asked "saved card ending 1003, or a different
  // card?". Nothing is booked yet — park what they asked for and bring the trip into view.
  const handleConfirmCard = useCallback((item: { offer_id: string; label: string; amount_usd: number; kind: string; name: string } | null, savedCard: { last4: string } | null) => {
    pendingCardRef.current = { item, savedCard }
    if (!item) handleTabChange('trip')
  }, [handleTabChange])

  // A TAP on Reserve (a card) or "Book the whole trip" (Trip tab) must feel exactly like the
  // spoken "book it": Sasha wakes up and asks which card to use, the guest answers by voice
  // (or types), and the same pay_saved_card / pay_new_card turn completes it. Nothing is
  // booked on the tap itself. The question is appended to the chat as Sasha's line so the
  // conductor sees "ending in 1003" as her last reply next turn — that is the whole handshake,
  // no backend call needed here. If she is mid-sentence the question queues behind it.
  const askCardChoice = useCallback((item: { offer_id: string; label: string; amount_usd: number; kind: string; name: string } | null) => {
    const subject = item ? item.name : 'your trip'
    const question = `Of course — let's get ${subject} booked. You have one saved card on file, ending in ${SAVED_CARD_LAST4}. Shall I go ahead and complete the payment automatically with that card, or would you like to pay with a different card?`
    pendingCardRef.current = { item, savedCard: { last4: SAVED_CARD_LAST4 } }
    setChatMessages(prev => [...prev, { role: 'assistant', content: question }])
    if (!item) handleTabChange('trip')
    if (isRespondingRef.current) pendingSpeechRef.current = question
    else speakNow(question)
  }, [handleTabChange, speakNow])

  // A guest tapped "Reserve" on an individual hotel/flight/cab card. Previously this reserved
  // on the spot (or opened the Stripe modal with payments on); now it hands off to Sasha's
  // card question so taps and voice converge on one flow.
  const handleBookItem = useCallback((offer: { offer_id: string; label: string; amount_usd: number; kind: string; name: string }) => {
    setCheckoutError(null)
    askCardChoice(offer)
  }, [askCardChoice])

  // Turn 2a: "use 1003" — complete the pending booking against the card on file. No Stripe,
  // no form: /api/payments/reserve records the card and mints the ref, and the confirmation
  // (and the Trip tab) read "Booked · Paid with card ending 1003".
  const handlePaySavedCard = useCallback((savedCard: { last4: string }) => {
    const pending = pendingCardRef.current
    pendingCardRef.current = null
    const card = savedCard?.last4 ? savedCard : (pending?.savedCard ?? savedCard)
    if (pending?.item) reserveItem(pending.item, card)
    else reserveTrip(card)
  }, [reserveItem, reserveTrip])

  // Turn 2b: "a different card" — open the payment form for whatever was pending. This is the
  // Stripe Checkout path and needs the payment service configured; the form itself explains
  // when it isn't ("Payments are not configured for this demo yet").
  const handlePayNewCard = useCallback(() => {
    const pending = pendingCardRef.current
    pendingCardRef.current = null
    setCheckoutError(null)
    if (pending?.item) setPendingOffer(pending.item)
    else { setPendingOffer(null); handleTabChange('trip') }
    setPaymentModal('card')
  }, [handleTabChange])

  // Open the booked itinerary as a printable page → user saves as PDF via the print dialog.
  const exportItineraryPdf = useCallback(() => {
    if (!richItinerary) return
    const html = buildItineraryHtml(richItinerary, booked?.ref, booked?.paidWith ?? null)
    const w = window.open('', '_blank')
    if (!w) { setShareToast('Allow pop-ups to download the PDF.'); setTimeout(() => setShareToast(null), 2500); return }
    w.document.open(); w.document.write(html); w.document.close(); w.focus()
    setTimeout(() => { try { w.print() } catch {} }, 500)
  }, [richItinerary, booked])

  // Native share sheet where available, else copy the itinerary text to the clipboard.
  const shareItinerary = useCallback(async () => {
    if (!richItinerary) return
    const text = buildItineraryText(richItinerary, booked?.ref, booked?.paidWith ?? null)
    const title = richItinerary.title || 'My Vietnam itinerary'
    try { if (navigator.share) { await navigator.share({ title, text }); return } } catch {}
    try { await navigator.clipboard.writeText(text); setShareToast('Itinerary copied to clipboard') }
    catch { setShareToast('Could not share automatically') }
    setTimeout(() => setShareToast(null), 2500)
  }, [richItinerary, booked])

  const handleSashaResponse = useCallback((text: string) => {
    if (!text) return
    // Never acquire the lock if there's no avatar speak fn to release it — that would
    // deadlock the whole conversation with nothing able to clear the lock.
    if (!speakFnRef.current) {
      console.warn('[LOCK] no speakFn wired — skipping avatar speak, not locking')
      return
    }
    // The avatar must SPEAK plain text — strip markdown so TTS never reads "asterisk".
    // The chat still displays the original markdown (rendered as bold/lists).
    const spoken = stripMarkdown(text)
    // If Sasha is mid-utterance — typically an interim "let me check that" line spoken while the
    // search ran — never cut her off. Queue the real answer; handleSashaFinished voices it the
    // instant she finishes, so the result is only spoken once her current sentence is over.
    if (isRespondingRef.current) {
      console.log('[LOCK] busy — queueing answer behind current utterance')
      pendingSpeechRef.current = spoken
      return
    }
    speakNow(spoken)
  }, [speakNow])

  // Context-driven interim speech: while a slow search/build runs, Sasha says what she's ACTUALLY
  // doing ("Let me check live flights for you") instead of going silent or reading a random
  // filler. SashaChat picks the line from the classified intent and passes it here; this only
  // speaks it, through the same locked speak path so the mic gate stays closed while she talks
  // and the real answer queues behind it (handleSashaResponse -> pendingSpeechRef). One per turn:
  // if she is already voicing something, skip — the answer will queue naturally.
  const handleInterim = useCallback((line: string) => {
    if (!line || isRespondingRef.current || !speakFnRef.current) return
    speakNow(line)
  }, [speakNow])


  // ── Mindtrip-style shell (2026-09-05), dark ─────────────────────────────────────────
  // Three columns: nav · centre STAGE · conversation. The avatar is ONE fixed element that
  // never remounts (a remount would restart the LiveAvatar session). On Chat it covers the
  // whole centre stage, full height; on Trip / Ideas / You the stage shows that panel (SashaChat
  // portals it in) and the avatar glides to a small picture-in-picture card in the stage's
  // bottom-right corner. Only top/left/width/height animate, so object-fit is preserved.
  const stageRef = useRef<HTMLDivElement | null>(null)
  const [panelHost, setPanelHost] = useState<HTMLDivElement | null>(null)
  const [avatarBox, setAvatarBox] = useState<{ top: number; left: number; width: number; height: number } | null>(null)
  // `?ui=preview` renders the shell with a placeholder tile and no live session — layout QA
  // without spending LiveAvatar credits. Read after mount so SSR and client agree.
  const [uiPreview, setUiPreview] = useState(false)
  useEffect(() => {
    try {
      const on = new URLSearchParams(window.location.search).get('ui') === 'preview'
      setUiPreview(on)
      if (on) setRichItinerary(PREVIEW_PLAN)   // layout QA only — never reached without the flag
    } catch {}
  }, [])
  const stageLive = started || uiPreview
  const avatarPip = stageLive && rightTab !== 'chat'
  const measureAvatar = useCallback(() => {
    const el = stageRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    if (r.width <= 0) return
    if (avatarPip) {
      const W = Math.max(200, Math.min(300, Math.round(r.width * 0.34)))
      const H = Math.round(W * 0.66)
      setAvatarBox({ top: r.bottom - H - 12, left: r.right - W - 12, width: W, height: H })
    } else {
      setAvatarBox({ top: r.top, left: r.left, width: r.width, height: r.height })
    }
  }, [avatarPip])
  useLayoutEffect(() => {
    measureAvatar()
    const raf = requestAnimationFrame(measureAvatar)
    const ro = stageRef.current ? new ResizeObserver(() => measureAvatar()) : null
    if (stageRef.current && ro) ro.observe(stageRef.current)
    window.addEventListener('resize', measureAvatar)
    return () => { cancelAnimationFrame(raf); ro?.disconnect(); window.removeEventListener('resize', measureAvatar) }
  }, [measureAvatar, stageLive, rightTab])
  // A destination chip tapped BEFORE the call starts: remember it and send it once the
  // session is up, so "Plan a 7 day trip" from the welcome screen becomes the first turn.
  const pendingOpenerRef = useRef<string | null>(null)
  useEffect(() => {
    if (started && voiceReady && pendingOpenerRef.current && sendChatRef.current) {
      const t = pendingOpenerRef.current; pendingOpenerRef.current = null
      sendChatRef.current(t)
    }
  }, [started, voiceReady])
  const startWith = useCallback((opener?: string) => {
    if (verifying || booked || itemBooked) return
    if (opener) pendingOpenerRef.current = opener
    handleStart()
  }, [verifying, booked, itemBooked, handleStart])
  const newChat = useCallback(() => {
    // Mindtrip's "New chat": a clean slate. Ending the live session first releases the
    // avatar; handleStart already resets messages/plan/tabs.
    if (started) handleEndSession()
    setTimeout(() => handleStart(), 60)
  }, [started, handleEndSession, handleStart])
  const NAV: { id: WorkspaceTab; label: string; Ic: React.ComponentType<{ size?: number; strokeWidth?: number }> }[] = [
    { id: 'chat', label: 'Chat', Ic: MessageSquare },
    { id: 'ideas', label: 'Ideas', Ic: Sparkles },
    { id: 'trip', label: 'Trip', Ic: MapIcon },
    { id: 'you', label: 'You', Ic: UserIcon },
  ]
  // The Live Workspace subtitle — what Sasha is doing right now (carried over from the old
  // workspace head so the copy stays familiar).
  const wsSubtitle = !started ? 'What Sasha is doing for you'
    : isAvatarSpeaking ? 'Speaking with you…'
    : richItinerary ? `Planning · ${richItinerary.title}`
    : photos.length > 0 ? `Exploring ${photos[activePhoto]?.location || photos[activePhoto]?.description || 'Vietnam'}`
    : 'What Sasha is doing for you'
  const statusLabel = micMuted ? 'Not listening' : isAvatarSpeaking ? 'Sasha is speaking' : isListening ? 'Listening…' : voiceConnected ? 'Mic live' : micError ? 'Mic unavailable' : 'Connecting…'

  return (
    <main className="mt-app">

      {/* ── LEFT NAV ── */}
      <aside className="mt-side">
        <div className="mt-brand">
          <LogoMark height={44} className="mt-logo" />
          <div className="mt-brand-sub"><VnFlag size={13} /><b>Discover Vietnam</b></div>
          <div className="mt-brand-sub">Sasha · AI travel concierge</div>
        </div>
        <nav className="mt-nav" aria-label="Workspace">
          {NAV.map(n => (
            <button key={n.id} className={`mt-navbtn ${rightTab === n.id ? 'on' : ''}`} onClick={() => handleTabChange(n.id)} aria-current={rightTab === n.id}>
              <span className="ic" aria-hidden><n.Ic size={16} strokeWidth={1.8} /></span><span className="lbl">{n.label}</span>
              {rightTab !== n.id && unseenTabs.includes(n.id) && <span className="dot" aria-label="Updated" />}
            </button>
          ))}
        </nav>
        <button className="mt-newchat" onClick={newChat}><Plus size={14} strokeWidth={2.2} /> New chat</button>
        <div className="mt-sidefoot">
          <select value={language} onChange={(e) => setLanguage(e.target.value)} title="Language Sasha speaks" className="mt-select">
            <option value="en">🇬🇧 English</option>
            <option value="vi">🇻🇳 Tiếng Việt</option>
            <option value="ko">🇰🇷 한국어</option>
            <option value="zh">🇨🇳 中文</option>
            <option value="ja">🇯🇵 日本語</option>
            <option value="fr">🇫🇷 Français</option>
            <option value="es">🇪🇸 Español</option>
          </select>
          {started && <button className="mt-end" onClick={handleEndSession} title="End the live avatar session to stop using credits">■ End session</button>}
          <div className="mt-partner">Ministry of Tourism Partner</div>
        </div>
      </aside>

      {/* ── CENTRE STAGE — the avatar, full height, on Chat; the open panel on Trip / Ideas / You ── */}
      <section className="mt-center">
        <div className="mt-top">
          <div className="mt-head">
            <span className="mt-head-ic"><Sparkles size={15} strokeWidth={1.8} /></span>
            <div style={{ minWidth: 0 }}>
              <div className="mt-title">{richItinerary ? richItinerary.title : 'New chat'}</div>
              <div className="mt-sub">{wsSubtitle}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {started ? (
              <span className="mt-pill live"><span className="la-dot" /> Live · {fmtTime(elapsed)}</span>
            ) : (
              <span className="mt-pill">Ready when you are</span>
            )}
            {started && <span className="mt-pill">{statusLabel}</span>}
          </div>
        </div>
        <div className="mt-stage" ref={stageRef}>
          {/* SashaChat portals Trip / Ideas / You in here; on Chat the fixed avatar covers this box. */}
          <div ref={setPanelHost} className="mt-panelhost" style={{ display: stageLive && rightTab !== 'chat' ? 'flex' : 'none' }} />
        </div>
      </section>

      {/* ── RIGHT — the conversation (transcript, cards, composer); the welcome before the call ── */}
      <aside className="mt-rail">
        <div className="mt-wshead">
          <div className="mt-head">
            <span className="mt-head-ic"><Sparkles size={15} strokeWidth={1.8} /></span>
            <div style={{ minWidth: 0 }}>
              <div className="mt-title">Live Workspace</div>
              <div className="mt-sub">{wsSubtitle}</div>
            </div>
          </div>
          {isAvatarSpeaking
            ? <span className="mt-pill gold"><span className="la-load"><i /><i /><i /></span> Sasha is responding</span>
            : <span className="mt-pill">Ready</span>}
        </div>
        {stageLive ? (
          <SashaChat
            user={DEMO_USER}
            onSashaResponse={handleSashaResponse}
            onListeningChange={setIsListening}
            onSetGate={handleSetGate}
            onInterrupt={handleInterrupt}
            onPhotos={handlePhotos}
            presetPrompts={PRESET_PROMPTS}
            messages={chatMessages}
            setMessages={setChatMessages}
            avatarSpeaking={isAvatarSpeaking}
            // Prefer what Sasha actually said (covers the greeting); fall back to the last
            // text we asked her to say if the buffer isn't wired yet.
            avatarSpeechGetter={() => {
              const spoken = avatarSaidRef.current?.() || ''
              return `${spoken} ${lastRepeatTextRef.current}`.trim()
            }}
            isRespondingRef={isRespondingRef}
            readyToListen={voiceReady}
            onThinking={handleInterim}
            onItinerary={handleItinerary}
            language={language}
            registerSend={registerSend}
            richItinerary={richItinerary}
            photos={photos}
            activePhoto={activePhoto}
            onSelectPhoto={setActivePhoto}
            onBook={() => askCardChoice(null)}
            onVoiceConnected={setVoiceConnected}
            onMicError={setMicError}
            onMicDevices={setMicDevices}
            onBooked={handleBooked}
            onAwaitPayment={handleAwaitPayment}
            onBookItem={handleBookItem}
            onConfirmCard={handleConfirmCard}
            onPaySavedCard={handlePaySavedCard}
            onPayNewCard={handlePayNewCard}
            paidWith={booked?.paidWith ?? null}
            onItineraryId={handleItineraryId}
            bookingRef={booked?.ref ?? null}
            activeTab={rightTab}
            onTabChange={handleTabChange}
            onMarkUnseen={markUnseen}
            onBuildingChange={handleBuildingChange}
            unseenTabs={unseenTabs}
            ideasCache={ideasCache}
            onIdeasCache={setIdeasCache}
            hideTabs
            panelPortal={panelHost}
          />
        ) : (
          <div className="mt-welcome-wrap">
            <div className="mt-welcome-scroll">
              <div className="mt-when">Where to?</div>
              <div className="mt-openers">
                {WELCOME_OPENERS.map((o, i) => (
                  <button key={o.location} className="mt-opener" onClick={() => startWith(o.ask)} style={{ animationDelay: `${i * 60}ms` }} title={o.ask}>
                    <img src={o.url} alt={o.location} loading="lazy" />
                    <span className="g" />
                    <span className="c"><b>{o.location}</b><span>{o.blurb}</span></span>
                  </button>
                ))}
              </div>
              <div className="mt-when">Or just ask</div>
              <div className="mt-chips">
                {PRESET_PROMPTS.map(pr => (
                  <button key={pr} className="mt-chip" onClick={() => startWith(pr)}>{pr}</button>
                ))}
              </div>
              {verifying && <div className="text-center text-sm" style={{ color: '#DAA520', marginTop: 10 }}>Confirming your payment…</div>}
            </div>
            <div className="mt-fakecomposer" onClick={() => startWith()} role="button" aria-label="Start your call with Sasha">
              <span className="mic"><Mic size={16} strokeWidth={2} /></span>
              <span className="in">Tap to start, then just talk or type…</span>
              <span className="go"><Send size={15} strokeWidth={2} /></span>
            </div>
          </div>
        )}
      </aside>

      {/* ── THE AVATAR — one fixed element: hero on Chat, PiP everywhere else ── */}
      <div
        className="mt-avatar"
        data-mode={avatarPip ? 'pip' : 'hero'}
        style={avatarBox ? { top: avatarBox.top, left: avatarBox.left, width: avatarBox.width, height: avatarBox.height } : { opacity: 0 }}
        onClick={avatarPip ? () => handleTabChange('chat') : undefined}
        title={avatarPip ? 'Back to Sasha' : undefined}
      >
        <div className="mt-glow" aria-hidden />
        <div className="mt-ring" aria-hidden />
        <div className="mt-ring mt-ring2" aria-hidden />
        <div className="absolute inset-0">
          {started && (
            <SashaAvatar
              key={language}
              tokenUrl={`/api/heygen/token?lang=${language}`}
              onAvatarReady={handleAvatarReady}
              isListening={isListening}
              onGate={handleGate}
              onAvatarSpeakingChange={setIsAvatarSpeaking}
              onReadyToListen={() => setVoiceReady(true)}
              onSashaFinished={handleSashaFinished}
              onAvatarSpeechBuffer={handleAvatarSpeechBuffer}
              hideStatusBadge
              bare
            />
          )}
          {!started && (
            <>
              {/* Standby: Sasha's own preview still, dimmed, on the same stage she will appear
                  on — so the call starts where the eye already is. (public/sasha-preview.jpg
                  is the LiveAvatar preview for the configured avatar; refresh it if the avatar
                  changes.) */}
              <img className="mt-standby" src="/sasha-preview.jpg" alt="" style={{ opacity: uiPreview ? 1 : .55, filter: uiPreview ? 'none' : 'saturate(.7)' }} />
              <div className="absolute inset-0 pointer-events-none" style={{ background: 'linear-gradient(to bottom, rgba(0,0,0,.55) 0%, transparent 22%, transparent 58%, rgba(0,0,0,.85) 100%)' }} />
              <div className="mt-ov-top absolute top-0 left-0 right-0 flex items-center" style={{ padding: '14px 16px', zIndex: 3 }}>
                <span className="mt-standbypill"><span className="mt-standbydot" /> {uiPreview ? 'Preview' : 'Standby'}</span>
              </div>
              {!uiPreview && (
                <div className="mt-startwrap">
                  <div className="mt-eyebrow">AI Travel Concierge</div>
                  <div className="mt-bigname">Meet Sasha</div>
                  <button className="mt-startbtn" onClick={() => startWith()}><Play size={16} strokeWidth={2.2} fill="#fff" /> Tap to start your call</button>
                  <div className="mt-hint">Audio plays automatically once you start</div>
                </div>
              )}
            </>
          )}
        </div>
    {started && (
      <>
        {/* gradient overlay for legibility */}
        <div className="absolute inset-0 pointer-events-none" style={{ background: 'linear-gradient(to bottom, rgba(0,0,0,.55) 0%, transparent 22%, transparent 55%, rgba(0,0,0,.85) 100%)' }} />

        {/* top status bar */}
        <div className="mt-ov-top absolute top-0 left-0 right-0 flex items-center justify-between" style={{ padding: '16px 18px', zIndex: 3 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, letterSpacing: '.12em', textTransform: 'uppercase', fontWeight: 600, color: '#fff', background: 'rgba(0,0,0,.35)', padding: '7px 12px', borderRadius: 999, border: '1px solid rgba(255,255,255,.1)', backdropFilter: 'blur(8px)' }}>
            <span className="la-dot" /> Live
            <span style={{ fontVariantNumeric: 'tabular-nums', color: 'rgba(255,255,255,.85)', fontSize: 12, marginLeft: 4 }}>{fmtTime(elapsed)}</span>
          </div>
          <button
            className="la-icon"
            title="End session"
            aria-label="End session"
            style={{ background: 'rgba(248,113,113,.9)', borderColor: 'transparent', padding: 0 }}
            onClick={handleEndSession}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round"><path d="M2 2l10 10M12 2L2 12" /></svg>
          </button>
        </div>

        {/* agent identity ribbon */}
        <div className="mt-ov-hero absolute flex items-center gap-2.5" style={{ left: 18, top: 62, zIndex: 3 }}>
          <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'linear-gradient(135deg,#8b5cf6,#6d28d9)', display: 'grid', placeItems: 'center', fontWeight: 700, fontSize: 13, border: '2px solid rgba(255,255,255,.25)' }}>S</div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14, lineHeight: 1 }}>Sasha</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,.6)', marginTop: 2 }}>Vietnam Specialist · concierge</div>
          </div>
        </div>

        {/* user camera PiP */}
        <div className="mt-ov-hero absolute overflow-hidden" style={{ right: 16, bottom: 96, width: 148, height: 104, borderRadius: 16, border: '2px solid rgba(255,255,255,.25)', boxShadow: '0 14px 40px -10px rgba(0,0,0,.8)', zIndex: 4, background: '#15151f' }}>
          <video
            ref={userVideoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover"
            style={{ display: camOn ? 'block' : 'none', transform: 'scaleX(-1)' }}
          />
          {!camOn && (
            <div className="w-full h-full flex flex-col items-center justify-center gap-2" style={{ background: 'linear-gradient(160deg,#1c1c28,#101018)' }}>
              <div style={{ width: 46, height: 46, borderRadius: '50%', background: 'rgba(255,255,255,.08)', display: 'grid', placeItems: 'center', fontSize: 22, color: 'rgba(255,255,255,.4)' }}>👤</div>
              <div style={{ fontSize: 10.5, color: 'rgba(255,255,255,.4)' }}>{camEnabled ? 'No camera' : 'Camera off'}</div>
            </div>
          )}
          <span style={{ position: 'absolute', left: 7, bottom: 6, fontSize: 10, fontWeight: 600, letterSpacing: '.05em', background: 'rgba(0,0,0,.55)', padding: '3px 7px', borderRadius: 6, backdropFilter: 'blur(4px)' }}>You</span>
        </div>

        {/* bottom: live caption + mic status */}
        <div className="mt-ov-hero absolute left-0 right-0 bottom-0 flex flex-col gap-3" style={{ padding: 18, zIndex: 3 }}>
          {caption && (
            <div style={{ maxWidth: '60%', fontSize: 14, lineHeight: 1.45, color: 'rgba(255,255,255,.92)', textShadow: '0 2px 12px rgba(0,0,0,.7)', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{caption}</div>
          )}
          {/* Call controls. Wraps as whole pills rather than letting any single pill
              squeeze and break its label across two lines, which is what happened once the
              mic picker joined the row in the narrow call panel. */}
          <div className="flex items-center" style={{ gap: 8, flexWrap: 'nowrap', overflow: 'hidden' }}>
            {/* Muted wins over every other state: the mic is genuinely closed, so a
                leftover "Listening…" equaliser would be actively lying to the guest. */}
            {micMuted ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: '#f87171', background: 'rgba(248,113,113,.12)', border: '1px solid rgba(248,113,113,.45)', borderRadius: 999, padding: '8px 14px', backdropFilter: 'blur(10px)', whiteSpace: 'nowrap', flexShrink: 1, minWidth: 0, overflow: 'hidden' }}>
                <MicOff className="w-3.5 h-3.5" /> Not listening — building your trip
              </div>
            ) : isAvatarSpeaking ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: '#DAA520', background: 'rgba(0,0,0,.4)', border: '1px solid rgba(218,165,32,.3)', borderRadius: 999, padding: '8px 14px', backdropFilter: 'blur(10px)', whiteSpace: 'nowrap', flexShrink: 1, minWidth: 0, overflow: 'hidden' }}>
                <span className="la-load"><i /><i /><i /></span> Sasha is speaking
              </div>
            ) : isListening ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 12.5, color: '#34d399', background: 'rgba(0,0,0,.4)', border: '1px solid rgba(52,211,153,.35)', borderRadius: 999, padding: '8px 14px', backdropFilter: 'blur(10px)', whiteSpace: 'nowrap', flexShrink: 1, minWidth: 0, overflow: 'hidden' }}>
                <span className="la-eq"><span /><span /><span /><span /></span> Listening…
              </div>
            ) : voiceConnected ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 12.5, color: 'rgba(255,255,255,.85)', background: 'rgba(0,0,0,.4)', border: '1px solid rgba(255,255,255,.14)', borderRadius: 999, padding: '8px 14px', backdropFilter: 'blur(10px)', whiteSpace: 'nowrap', flexShrink: 1, minWidth: 0, overflow: 'hidden' }}>
                <span className="la-dot" /> Mic live — just talk
              </div>
            ) : micError ? (
              // Tell the guest what's wrong and what to do — and keep the session usable:
              // Sasha still speaks, and the composer still takes typed messages.
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 12.5, color: '#f87171', background: 'rgba(248,113,113,.12)', border: '1px solid rgba(248,113,113,.4)', borderRadius: 999, padding: '8px 14px', backdropFilter: 'blur(10px)', whiteSpace: 'nowrap', flexShrink: 1, minWidth: 0, overflow: 'hidden' }}>
                <span>🚫</span>
                {micError === 'Mic permission denied'
                  ? 'Mic blocked — allow it in your browser, or type below'
                  : `${micError} — you can type below`}
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 12.5, color: 'rgba(255,255,255,.6)', background: 'rgba(0,0,0,.4)', border: '1px solid rgba(255,255,255,.12)', borderRadius: 999, padding: '8px 14px', backdropFilter: 'blur(10px)', whiteSpace: 'nowrap', flexShrink: 1, minWidth: 0, overflow: 'hidden' }}>
                <span className="la-load"><i /><i /><i /></span> Starting microphone…
              </div>
            )}

            {/* Camera toggle — stops the tracks rather than hiding the element, so the
                camera light actually goes out when the guest turns it off. */}
            <button
              onClick={() => setCamEnabled(v => !v)}
              aria-pressed={camEnabled}
              title={camEnabled ? 'Turn camera off' : 'Turn camera on'}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, cursor: 'pointer',
                background: camEnabled ? 'rgba(0,0,0,.4)' : 'rgba(248,113,113,.12)',
                border: `1px solid ${camEnabled ? 'rgba(255,255,255,.14)' : 'rgba(248,113,113,.4)'}`,
                color: camEnabled ? 'rgba(255,255,255,.85)' : '#f87171',
                // Never shrinks: it is a control, not a label. Only the status pill gives
                // way when the row is tight.
                borderRadius: 999, padding: '8px 14px', backdropFilter: 'blur(10px)', whiteSpace: 'nowrap', flexShrink: 0,
              }}
            >
              {camEnabled ? '📹 Camera on' : '🚫 Camera off'}
            </button>

            {/* Mic picker — same pill as the camera toggle so the call controls read as one
                row. Only appears once there are two or more named inputs (see VoiceButton),
                which is exactly when a guest can be stuck on a Continuity/phone mic. */}
            {micDevices && (
              <select
                aria-label="Microphone"
                title="Choose which microphone Sasha listens to"
                value={micDevices.selectedId}
                onChange={(e) => micDevices.switchMic(e.target.value)}
                // The one control allowed to shrink: device names are long and unbounded,
                // so it truncates rather than pushing the fixed-width pills out of the row.
                style={{
                  // alignSelf:stretch + zero vertical padding is what makes a <select>
                  // match the pills exactly: its intrinsic line metrics otherwise render
                  // it ~2px shorter and 1px lower than the buttons beside it.
                  alignSelf: 'stretch', lineHeight: 1,
                  flexShrink: 0, maxWidth: 168,
                  fontSize: 12.5, cursor: 'pointer', outline: 'none',
                  background: 'rgba(0,0,0,.4)',
                  border: '1px solid rgba(255,255,255,.14)',
                  color: 'rgba(255,255,255,.85)',
                  borderRadius: 999, padding: '0 12px', backdropFilter: 'blur(10px)',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
              >
                <option value="">🎤 Mic: Auto</option>
                {micDevices.devices.map((d, i) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {(d.isPhone ? '📱 ' : '🎤 ') + micLabel(d.label, i)}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
      </>
    )}

        {started && avatarPip && (
          <div className="mt-pipfoot">
            <b>Sasha</b>
            <span className="x">{statusLabel} · tap to expand</span>
          </div>
        )}
      </div>

      {reserveError && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] px-5 py-3 rounded-xl text-sm shadow-xl"
          style={{ background: 'rgba(248,113,113,0.95)', color: '#fff' }}>
          {reserveError}
        </div>
      )}

      {payResult && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] px-5 py-3 rounded-xl text-sm shadow-xl"
          style={{
            background: payResult === 'paid' ? 'rgba(16,185,129,0.95)' : 'rgba(248,113,113,0.95)',
            color: '#fff',
          }}
          onAnimationEnd={() => {}}
        >
          {payResult === 'paid' ? '✓ Payment received — your booking is confirmed.' : 'Payment canceled — tap to start and Sasha will pick your trip right back up.'}
          <button onClick={() => setPayResult(null)} className="ml-3 opacity-70 hover:opacity-100">✕</button>
        </div>
      )}

      {paymentModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.7)' }} onClick={() => { setPaymentModal(null); setPendingOffer(null) }}>
          <div className="rounded-2xl p-6 w-96 shadow-xl" style={{ background: '#1a1a2e', border: '1px solid rgba(218,165,32,0.3)' }} onClick={e => e.stopPropagation()}>
            <div className="text-lg font-semibold mb-1" style={{ color: '#DAA520' }}>Complete Booking</div>
            {pendingOffer ? (
              <div className="text-sm mb-5" style={{ color: 'rgba(255,255,255,0.4)' }}>{pendingOffer.label} · <span style={{ color: '#E8B923', fontWeight: 600 }}>${pendingOffer.amount_usd.toLocaleString()}</span></div>
            ) : (
              <div className="text-sm mb-5" style={{ color: 'rgba(255,255,255,0.4)' }}>Total: ${(richItinerary?.estimated_total_usd || 0).toLocaleString()}</div>
            )}

            {paymentModal === 'card' ? (
              <>
                <div className="text-xs mb-3" style={{ color: 'rgba(255,255,255,0.45)' }}>
                  Confirm your details, then continue to our secure Stripe checkout.
                </div>
                <input
                  value={payerName} onChange={(e) => setPayerName(e.target.value)}
                  placeholder="Full name (for the reservation)"
                  className="w-full mb-2 px-3 py-2 rounded-xl text-sm outline-none"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' }}
                />
                <input
                  value={payerEmail} onChange={(e) => setPayerEmail(e.target.value)}
                  type="email" placeholder="Email (for confirmation)"
                  className="w-full mb-3 px-3 py-2 rounded-xl text-sm outline-none"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' }}
                />
                {checkoutError && (
                  <div className="text-xs mb-3 px-3 py-2 rounded-lg" style={{ background: 'rgba(248,113,113,0.12)', color: '#f87171' }}>{checkoutError}</div>
                )}
                <div className="flex gap-3 mt-2">
                  <button onClick={() => { setCheckoutError(null); setPaymentModal(null); setPendingOffer(null) }} disabled={checkoutLoading} className="flex-1 py-3 rounded-xl text-sm disabled:opacity-40" style={{ border: '1px solid rgba(218,165,32,0.2)', color: 'rgba(255,255,255,0.6)' }}>Cancel</button>
                  <button onClick={startCardCheckout} disabled={checkoutLoading} className="flex-1 py-3 rounded-xl text-sm font-medium disabled:opacity-60" style={{ background: 'linear-gradient(135deg, #DAA520, #B8860B)', color: 'white' }}>
                    {checkoutLoading ? 'Starting…' : 'Pay securely'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="text-xs mb-4" style={{ color: 'rgba(255,255,255,0.45)' }}>
                  Crypto payments are coming soon. Use card to complete this booking today.
                </div>
                <div className="flex gap-3 mt-2">
                  <button onClick={() => { setPaymentModal(null); setPendingOffer(null) }} className="flex-1 py-3 rounded-xl text-sm" style={{ border: '1px solid rgba(218,165,32,0.2)', color: 'rgba(255,255,255,0.6)' }}>Close</button>
                  <button onClick={() => { setCheckoutError(null); setPaymentModal('card') }} className="flex-1 py-3 rounded-xl text-sm font-medium" style={{ background: 'linear-gradient(135deg, #DAA520, #B8860B)', color: 'white' }}>Pay by card</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Single-item booking confirmation (hotel / flight / cab) — a compact receipt, distinct
          from the full-trip confirmation below. Reached via the Stripe return leg when verify
          returns an `item`. */}
      {itemBooked && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" style={{ background: 'rgba(6,6,12,0.94)', backdropFilter: 'blur(14px)' }} onClick={() => setItemBooked(null)}>
          <div className="relative flex flex-col overflow-hidden" style={{ width: 'min(440px, 96vw)', borderRadius: 24, border: '1px solid rgba(218,165,32,0.3)', background: 'linear-gradient(180deg, rgba(218,165,32,0.06), rgba(0,0,0,0.25)), #0e0e16', boxShadow: '0 40px 100px -30px rgba(0,0,0,.9)' }} onClick={e => e.stopPropagation()}>
            <div className="text-center" style={{ padding: '28px 24px 24px' }}>
              <div style={{ width: 56, height: 56, borderRadius: '50%', margin: '0 auto 14px', display: 'grid', placeItems: 'center', background: 'rgba(52,211,153,0.14)', border: '1px solid rgba(52,211,153,0.4)', fontSize: 26, color: '#34d399' }}>✓</div>
              <div style={{ fontSize: 21, fontWeight: 700, color: '#fff', letterSpacing: '-0.01em' }}>
                {(() => {
                  const w = itemBooked.paidWith ? 'booked' : 'reserved'
                  return itemBooked.kind === 'hotel' ? `Stay ${w}!` : itemBooked.kind === 'flight' ? `Flight ${w}!` : itemBooked.kind === 'cab' ? `Transfer ${w}!` : itemBooked.kind === 'restaurant' ? `Table ${w}!` : itemBooked.paidWith ? 'Booked!' : 'Reserved!'
                })()}
              </div>
              <div style={{ fontSize: 13.5, color: 'rgba(255,255,255,.6)', marginTop: 8 }}>
                {(itemBooked.kind === 'hotel' ? '🏨 ' : itemBooked.kind === 'flight' ? '✈️ ' : itemBooked.kind === 'cab' ? '🚕 ' : itemBooked.kind === 'restaurant' ? '🍽️ ' : '')}{itemBooked.label}
              </div>
              {typeof itemBooked.amount === 'number' && (
                <div style={{ fontSize: 15, fontWeight: 700, color: '#E8B923', marginTop: 6 }}>${itemBooked.amount.toLocaleString()}{(PAYMENTS_ENABLED || itemBooked.paidWith) ? ' paid' : ''}</div>
              )}
              <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,.45)', marginTop: 8 }}>
                {itemBooked.paidWith ? (itemBooked.paidWith.last4 ? `Booking confirmed · paid with your card ending ${itemBooked.paidWith.last4}.` : 'Booking confirmed and paid.') : 'Your reservation is confirmed.'}{itemBooked.emailSent ? ' A confirmation is on its way to your email.' : ''}
              </div>
              {itemBooked.ref && (
                <div style={{ display: 'inline-block', marginTop: 12, fontSize: 12.5, fontWeight: 600, color: '#E8B923', background: 'rgba(218,165,32,0.1)', border: '1px solid rgba(218,165,32,0.3)', borderRadius: 8, padding: '6px 12px' }}>{itemBooked.paidWith ? 'Booking' : 'Reservation'} · {itemBooked.ref}</div>
              )}
              <div style={{ marginTop: 20 }}>
                <button onClick={() => setItemBooked(null)} style={{ padding: '11px 28px', borderRadius: 12, border: 'none', background: 'linear-gradient(135deg, #DAA520, #B8860B)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>Done</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Booking confirmation — final itinerary, shareable / exportable as PDF */}
      {booked && richItinerary && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" style={{ background: 'rgba(6,6,12,0.94)', backdropFilter: 'blur(14px)' }}>
          <div className="relative flex flex-col overflow-hidden" style={{ width: 'min(680px, 96vw)', maxHeight: '92vh', borderRadius: 24, border: '1px solid rgba(218,165,32,0.3)', background: 'linear-gradient(180deg, rgba(218,165,32,0.06), rgba(0,0,0,0.25)), #0e0e16', boxShadow: '0 40px 100px -30px rgba(0,0,0,.9)' }}>
            <div className="flex-shrink-0 text-center" style={{ padding: '26px 24px 18px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <div style={{ width: 56, height: 56, borderRadius: '50%', margin: '0 auto 14px', display: 'grid', placeItems: 'center', background: 'rgba(52,211,153,0.14)', border: '1px solid rgba(52,211,153,0.4)', fontSize: 26, color: '#34d399' }}>✓</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#fff', letterSpacing: '-0.01em' }}>{booked.paidWith ? 'Trip booked!' : 'Trip reserved!'}</div>
              {/* Only promise an email when one actually went out — the send is best-effort
                  and silently no-ops without RESEND_API_KEY. */}
              <div style={{ fontSize: 13, color: 'rgba(255,255,255,.5)', marginTop: 5 }}>
                {booked.paidWith
                  ? `Your booking is confirmed and paid${booked.paidWith.last4 ? ` with your card ending ${booked.paidWith.last4}` : ''} — your full itinerary is below.`
                  : 'Your reservation is confirmed — your full itinerary is below.'}
                {booked.emailSent ? ' A confirmation is on its way to your email.' : ''}
              </div>
              {booked.ref && (
                <div style={{ display: 'inline-block', marginTop: 12, fontSize: 12.5, fontWeight: 600, color: '#E8B923', background: 'rgba(218,165,32,0.1)', border: '1px solid rgba(218,165,32,0.3)', borderRadius: 8, padding: '6px 12px' }}>{booked.paidWith ? 'Booking' : 'Reservation'} · {booked.ref}</div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto" style={{ padding: '18px 22px' }}>
              <div style={{ fontSize: 17, fontWeight: 700, color: '#DAA520', marginBottom: 2 }}>{richItinerary.title}</div>
              {richItinerary.summary && <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,.5)', marginBottom: 14 }}>{richItinerary.summary}</div>}
              {richItinerary.days?.map(d => (
                <div key={d.day} className="flex items-start gap-3" style={{ padding: '10px 0', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ width: 26, height: 26, borderRadius: 8, background: 'rgba(218,165,32,0.12)', color: '#DAA520', display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>{d.day}</div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: '#fff' }}>{d.title}</div>
                    <div style={{ fontSize: 12, color: 'rgba(255,255,255,.5)', marginTop: 1 }}>📍 {d.city}{(d.hotel as any)?.name ? ` · ${(d.hotel as any).name}` : ''}</div>
                  </div>
                  <div style={{ fontSize: 11.5, color: 'rgba(255,255,255,.3)', whiteSpace: 'nowrap' }}>Day {d.day}</div>
                </div>
              ))}
              <div className="flex items-center justify-between" style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                {/* Fall back to who's actually on the booking rather than asserting "2
                    travellers" on a confirmation the guest is about to pay for. */}
                {(() => {
                  const pax = (richItinerary as any).cost_breakdown?.travellers || DEMO_USER.travellers?.length || 1
                  return <span style={{ fontSize: 12.5, color: 'rgba(255,255,255,.5)' }}>Total · {pax} traveller{pax > 1 ? 's' : ''}</span>
                })()}
                <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: 24, color: '#E8B923' }}>${(richItinerary.estimated_total_usd || 0).toLocaleString()}</span>
              </div>
            </div>

            <div className="flex-shrink-0 flex gap-3" style={{ padding: '16px 22px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <button onClick={shareItinerary} className="flex-1" style={{ padding: '12px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(255,255,255,0.04)', color: '#fff', fontSize: 13.5, fontWeight: 600, cursor: 'pointer' }}>↗ Share</button>
              <button onClick={exportItineraryPdf} className="flex-1" style={{ padding: '12px', borderRadius: 12, border: 'none', background: 'linear-gradient(135deg,#DAA520,#B8860B)', color: '#fff', fontSize: 13.5, fontWeight: 600, cursor: 'pointer' }}>⬇ Download PDF</button>
              <button onClick={() => { endOnFinishRef.current = false; clearTimeout(bookEndTimerRef.current); if (started) handleEndSession(); setBooked(null) }} style={{ padding: '12px 16px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.1)', background: 'transparent', color: 'rgba(255,255,255,.55)', fontSize: 13.5, cursor: 'pointer' }}>Done</button>
            </div>
          </div>
          {shareToast && (
            <div className="fixed bottom-6 left-1/2 -translate-x-1/2" style={{ background: 'rgba(0,0,0,0.85)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 999, padding: '9px 16px', fontSize: 12.5, color: '#fff' }}>{shareToast}</div>
          )}
        </div>
      )}


      <style jsx global>{`
        /* Prevent this page from covering a parent iframe's nav when embedded */
        :fullscreen, ::backdrop { display: none !important; }
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
        @keyframes pulse {
          0%, 100% { box-shadow: 0 8px 32px rgba(218,165,32,0.35); }
          50% { box-shadow: 0 8px 48px rgba(218,165,32,0.6); }
        }

        /* Video-call chrome (mockup UI) */
        .la-dot{width:8px;height:8px;border-radius:50%;background:#34d399;box-shadow:0 0 0 0 rgba(52,211,153,.7);animation:laPulse 2s infinite;display:inline-block}
        @keyframes laPulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.6)}70%{box-shadow:0 0 0 7px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
        .la-icon{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;cursor:pointer;background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.1);backdrop-filter:blur(8px);color:#fff;font-size:15px;transition:.2s}
        .la-icon:hover{filter:brightness(1.15)}
        .la-eq{display:flex;align-items:flex-end;gap:2px;height:14px}
        .la-eq span{width:3px;background:#34d399;border-radius:2px;animation:laEq 1s infinite ease-in-out}
        .la-eq span:nth-child(1){animation-delay:-.4s}.la-eq span:nth-child(2){animation-delay:-.2s}.la-eq span:nth-child(3){animation-delay:-.6s}.la-eq span:nth-child(4){animation-delay:-.1s}
        @keyframes laEq{0%,100%{height:4px}50%{height:14px}}
        .la-load{display:inline-flex;gap:3px;align-items:center}
        .la-load i{width:5px;height:5px;border-radius:50%;background:#DAA520;display:inline-block;animation:laBounce 1.2s infinite}
        .la-load i:nth-child(2){animation-delay:.15s}.la-load i:nth-child(3){animation-delay:.3s}
        @keyframes laBounce{0%,100%{opacity:.3;transform:translateY(0)}50%{opacity:1;transform:translateY(-3px)}}

        /* ── Mindtrip-style shell, dark & compact ── */
        .mt-app{height:100vh;display:flex;background:radial-gradient(1200px 800px at 18% -10%, #15131f 0%, #07070d 55%);color:#fff;overflow:hidden}
        .mt-side{width:196px;flex-shrink:0;display:flex;flex-direction:column;padding:12px 10px;border-right:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.35)}
        .mt-brand{display:flex;flex-direction:column;gap:7px;padding:4px 6px 14px}
        .mt-logo{mix-blend-mode:screen;margin-left:-6px}
        .mt-brand-sub{display:flex;align-items:center;gap:7px;font-size:9.5px;letter-spacing:.07em;text-transform:uppercase;color:rgba(255,255,255,.45);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .mt-brand-sub b{color:#DAA520;font-weight:700;letter-spacing:.04em;font-size:12.5px;text-transform:none}
        .mt-nav{display:flex;flex-direction:column;gap:2px}
        .mt-navbtn{display:flex;align-items:center;gap:10px;width:100%;border:0;background:none;cursor:pointer;font:inherit;font-size:13.5px;font-weight:500;color:rgba(255,255,255,.6);padding:9px 10px;border-radius:10px;text-align:left;position:relative;transition:background .15s,color .15s}
        .mt-navbtn:hover{background:rgba(255,255,255,.05);color:#fff}
        .mt-navbtn.on{background:rgba(218,165,32,.14);color:#E8B923;box-shadow:inset 0 0 0 1px rgba(218,165,32,.3)}
        .mt-navbtn .ic{width:20px;display:grid;place-items:center}
        .mt-navbtn .dot{position:absolute;right:10px;top:50%;width:6px;height:6px;margin-top:-3px;border-radius:50%;background:#DAA520;animation:lwPing 2s infinite}
        .mt-newchat{margin-top:10px;width:100%;display:flex;align-items:center;justify-content:center;gap:7px;padding:9px;border-radius:999px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05);color:#fff;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer}
        .mt-newchat:hover{background:rgba(255,255,255,.09)}
        .mt-sidefoot{margin-top:auto;display:flex;flex-direction:column;gap:8px;padding:0 2px}
        .mt-select{font:inherit;font-size:12px;padding:7px 9px;border-radius:999px;border:1px solid rgba(218,165,32,.3);background:rgba(218,165,32,.12);color:#DAA520;width:100%;cursor:pointer;outline:none}
        .mt-end{border:1px solid rgba(248,113,113,.35);color:#f87171;background:rgba(248,113,113,.1);border-radius:999px;padding:7px 10px;font:inherit;font-size:12px;font-weight:600;cursor:pointer;text-align:left}
        .mt-partner{font-size:9px;color:rgba(255,255,255,.3);letter-spacing:.05em;text-transform:uppercase;padding:2px 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .mt-center{flex:1;min-width:0;display:flex;flex-direction:column}
        .mt-top{display:flex;align-items:center;justify-content:space-between;padding:8px 12px 8px 14px;flex-shrink:0}
        .mt-head{display:flex;align-items:center;gap:10px;min-width:0}
        .mt-head-ic{width:28px;height:28px;border-radius:9px;background:rgba(218,165,32,.12);display:grid;place-items:center;color:#DAA520;flex-shrink:0}
        .mt-sub{font-size:11px;color:rgba(255,255,255,.35);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px}
        .mt-title{font-size:13.5px;font-weight:600;letter-spacing:.02em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fff}
        .mt-pill{display:inline-flex;align-items:center;gap:7px;font-size:11.5px;font-weight:500;padding:6px 11px;border-radius:999px;border:1px solid rgba(255,255,255,.1);color:rgba(255,255,255,.7);background:rgba(0,0,0,.3);white-space:nowrap}
        .mt-pill.live{color:#34d399;border-color:rgba(52,211,153,.35)}
        .mt-pill.gold{color:#DAA520;border-color:rgba(218,165,32,.3);background:rgba(218,165,32,.12)}
        /* The stage: measured for the avatar's hero box; hosts the portaled panels otherwise. */
        .mt-stage{flex:1;min-height:0;position:relative;margin:0 8px 10px 12px}
        .mt-panelhost{position:absolute;inset:0;flex-direction:column;border-radius:26px;border:1px solid rgba(255,255,255,.07);overflow:hidden;background:radial-gradient(700px 380px at 80% -8%, rgba(218,165,32,0.07), transparent 60%), linear-gradient(180deg,rgba(255,255,255,0.02),rgba(0,0,0,0.22))}
        .mt-rail{width:min(412px,36vw);flex-shrink:0;display:flex;flex-direction:column;min-height:0;margin:0 12px 10px 4px;border-radius:26px;border:1px solid rgba(255,255,255,.07);overflow:hidden;background:linear-gradient(180deg,rgba(255,255,255,0.02),rgba(0,0,0,0.22))}
        .mt-rail>.flex.flex-col.h-full{flex:1;min-height:0}
        .mt-rail .lw-chip{display:none}
        .mt-wshead{flex-shrink:0;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.25)}
        .mt-welcome-wrap{flex:1;min-height:0;display:flex;flex-direction:column}
        .mt-welcome-scroll{flex:1;min-height:0;overflow-y:auto;padding:16px 16px 12px;display:flex;flex-direction:column;gap:12px}
        .mt-when{display:flex;align-items:center;gap:12px;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.35)}
        .mt-when::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,rgba(255,255,255,.12),transparent)}
        .mt-openers{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
        .mt-opener{position:relative;display:block;padding:0;border:1px solid rgba(255,255,255,.08);border-radius:14px;overflow:hidden;aspect-ratio:3/2;cursor:pointer;background:rgba(255,255,255,.04);text-align:left;font:inherit;color:#fff;opacity:0;animation:mt-op-in .45s ease forwards}
        @keyframes mt-op-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
        .mt-opener img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .5s ease}
        .mt-opener:hover img{transform:scale(1.07)}
        .mt-opener:hover{border-color:rgba(218,165,32,.55)}
        .mt-opener .g{position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.85) 0%,rgba(0,0,0,.25) 45%,transparent 75%)}
        .mt-opener .c{position:absolute;left:0;right:0;bottom:0;padding:9px 10px;display:flex;flex-direction:column;gap:2px}
        .mt-opener .c b{font-size:14px;font-weight:650;letter-spacing:.01em}
        .mt-opener .c span{font-size:10.5px;color:rgba(255,255,255,.62);line-height:1.35}
        .mt-chips{display:flex;flex-wrap:wrap;gap:7px}
        .mt-chip{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.02);color:rgba(255,255,255,.6);border-radius:999px;padding:7px 12px;font:inherit;font-size:11.5px;cursor:pointer;transition:.2s}
        .mt-chip:hover{border-color:rgba(218,165,32,.4);color:#DAA520}
        .mt-fakecomposer{flex-shrink:0;margin:0;padding:12px 14px;border-top:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.2);display:flex;align-items:center;gap:9px;cursor:pointer}
        .mt-fakecomposer .mic{width:40px;height:40px;border-radius:50%;background:#4f46e5;display:grid;place-items:center;color:#fff;flex-shrink:0}
        .mt-fakecomposer .in{flex:1;font-size:13.5px;color:rgba(255,255,255,.3)}
        .mt-fakecomposer .go{width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,#DAA520,#B8860B);display:grid;place-items:center;color:#fff;flex-shrink:0}
        /* The avatar element itself. Hero ↔ PiP is a pure geometry transition. */
        .mt-avatar{position:fixed;z-index:40;overflow:hidden;border-radius:22px;border:1px solid rgba(255,255,255,.07);background:linear-gradient(160deg,#12101b,#0a0a12);color:#fff;box-shadow:0 30px 80px -30px rgba(0,0,0,.8);transition:top .5s cubic-bezier(.2,.8,.2,1),left .5s cubic-bezier(.2,.8,.2,1),width .5s cubic-bezier(.2,.8,.2,1),height .5s cubic-bezier(.2,.8,.2,1),border-radius .5s,opacity .3s}
        .mt-avatar[data-mode="pip"]{border-radius:16px;border-color:rgba(255,255,255,.14);box-shadow:0 24px 60px -20px rgba(0,0,0,.9);cursor:pointer}
        .mt-avatar[data-mode="pip"] .mt-ov-hero{display:none}
        .mt-avatar[data-mode="pip"] .mt-ov-top{padding:8px 10px!important}
        .mt-avatar[data-mode="pip"] .mt-ov-top .la-icon{width:24px;height:24px}
        .mt-pipfoot{position:absolute;left:0;right:0;bottom:0;padding:9px 11px;display:flex;align-items:center;justify-content:space-between;gap:8px;z-index:3;font-size:11px;color:#fff;background:linear-gradient(to top,rgba(0,0,0,.8),transparent)}
        .mt-pipfoot b{font-weight:600}
        .mt-pipfoot .x{opacity:.75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .mt-glow{position:absolute;inset:0;pointer-events:none;background:radial-gradient(560px 420px at 50% 62%,rgba(218,165,32,.16),transparent 70%),radial-gradient(420px 360px at 22% 20%,rgba(109,40,217,.22),transparent 70%),radial-gradient(360px 300px at 82% 18%,rgba(139,92,246,.14),transparent 70%)}
        .mt-ring{position:absolute;left:50%;top:60%;width:640px;height:640px;transform:translate(-50%,-50%);border-radius:50%;border:1px solid rgba(218,165,32,.12);box-shadow:inset 0 0 120px rgba(218,165,32,.06);pointer-events:none}
        .mt-ring2{width:880px;height:880px;border-color:rgba(255,255,255,.04);box-shadow:none}
        .mt-avatar[data-mode="pip"] .mt-ring{width:260px;height:260px}
        .mt-avatar[data-mode="pip"] .mt-ring2{width:360px;height:360px}
        .mt-standby{position:absolute;left:50%;bottom:0;transform:translateX(-50%);height:92%;width:auto;max-width:none;mix-blend-mode:screen;pointer-events:none;transition:opacity .4s}
        .mt-standbypill{display:inline-flex;align-items:center;gap:8px;font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;color:rgba(255,255,255,.7);background:rgba(0,0,0,.35);padding:7px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.1);backdrop-filter:blur(8px)}
        .mt-standbydot{width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.35);display:inline-block}
        .mt-startwrap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;padding-bottom:56px;gap:10px;text-align:center;z-index:3}
        .mt-eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:rgba(255,255,255,.45)}
        .mt-bigname{font-family:'Playfair Display',Georgia,serif;font-size:34px;font-weight:600;letter-spacing:-.01em;color:#fff;text-shadow:0 2px 24px rgba(0,0,0,.6)}
        .mt-startbtn{display:flex;align-items:center;gap:12px;margin-top:6px;padding:15px 34px;border-radius:16px;border:0;background:linear-gradient(135deg,#DAA520,#B8860B);color:#fff;font:inherit;font-size:16px;font-weight:700;cursor:pointer;box-shadow:0 8px 32px rgba(218,165,32,.35);animation:pulse 2s ease-in-out infinite}
        .mt-hint{font-size:12px;color:rgba(255,255,255,.35)}
        @media (max-width:1100px){.mt-rail{width:min(360px,42vw)}}
        @media (max-width:880px){
          .mt-side{width:58px;padding:10px 6px}
          .mt-side .lbl,.mt-brand-sub,.mt-sidefoot,.mt-newchat{display:none}
          .mt-navbtn{justify-content:center;padding:9px}
          .mt-rail{width:46vw}
        }
      `}</style>
    </main>
  )
}

