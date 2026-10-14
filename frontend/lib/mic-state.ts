/**
 * Sasha 266 · row 943 (a) — Tyler's iPhone (14 Oct 16:55–16:59Z): 16 Deepgram keys minted, NO socket reached Deepgram, the browser
 * never asked for the microphone, and the page looked "on". THE MIC IS "ON" ONLY WHEN IT HEARS: a live audio track delivering frames
 * (VoiceButton's `hearing`). Anything else is the plain stuck state, said on the page with the steps for THIS browser.
 *
 *   micPermission()   navigator.permissions' microphone state ("granted" | "denied" | "prompt" | null when the browser can't say)
 *   BLOCKED           the stuck line
 *   stepsFor(ua)      how to allow the microphone for this site, in this browser
 *   report(ev, data)  the mic's own state changes to the server (POST /api/voice/mic-event: no audio, no words, never a transcript) —
 *                     so a device that fails says how; at most REPORT_MAX per page
 */
import { apiUrl } from '@/lib/api'

export const BLOCKED = 'I can’t hear you — allow the microphone for this site'

export async function micPermission(): Promise<'granted' | 'denied' | 'prompt' | null> {
  try {
    const p = await navigator.permissions?.query({ name: 'microphone' as PermissionName })
    return (p?.state as 'granted' | 'denied' | 'prompt') ?? null
  } catch {
    return null   // Safari before 16 and some webviews can't answer: then the request itself says
  }
}

export function stepsFor(ua: string = typeof navigator !== 'undefined' ? navigator.userAgent : ''): string {
  if (/iPhone|iPad|iPod/.test(ua)) {
    return /CriOS/.test(ua)
      ? 'On your iPhone: Settings › Apps › Chrome › Microphone on, then reload this page.'
      : 'On your iPhone: tap “aA” in the address bar › Website Settings › Microphone › Allow — or Settings › Apps › Safari › Microphone › Ask. Then reload.'
  }
  if (/Android/.test(ua)) return 'On your phone: tap ⋮ › Settings › Site settings › Microphone › allow this site, then reload.'
  if (/Firefox\//.test(ua)) return 'In Firefox: click the microphone icon left of the address › allow, then reload.'
  if (/Safari\//.test(ua) && !/Chrome\//.test(ua)) return 'In Safari: Safari › Settings for this Website › Microphone › Allow, then reload.'
  return 'In your browser: click the icon left of the address › Microphone › Allow, then reload.'
}

const REPORT_MAX = 40
let reported = 0
const KEEP = ['name', 'message', 'state', 'status', 'why', 'perm', 'after', 'ms', 'by', 'frames']

export function report(ev: string, data: Record<string, unknown> = {}): void {
  if (typeof window === 'undefined' || reported >= REPORT_MAX) return
  reported++
  const body: Record<string, unknown> = { ev, page: location.pathname, ua: navigator.userAgent.slice(0, 180), t: Math.round(performance.now()) }
  for (const k of KEEP) if (data[k] !== undefined) body[k] = typeof data[k] === 'string' ? String(data[k]).slice(0, 120) : data[k]
  try {
    const blob = new Blob([JSON.stringify(body)], { type: 'text/plain' })   // a simple request: no preflight, survives the page closing
    if (!navigator.sendBeacon?.(apiUrl('/api/voice/mic-event'), blob)) {
      void fetch(apiUrl('/api/voice/mic-event'), { method: 'POST', body: JSON.stringify(body), keepalive: true }).catch(() => {})
    }
  } catch { /* never the mic's problem */ }
}
