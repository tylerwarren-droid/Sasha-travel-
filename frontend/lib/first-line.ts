/**
 * Sasha 265 · item 5 (row 935, Tyler: "an IMMEDIATE first line, under 1 s") — voice.first_line, read from the backend ONCE
 * (GET /api/agent/first-line: its words and its rule for a request for work). The page says it the instant such a request is sent;
 * the stream's own first line (`first: true`) is the same words and is then not said twice. One truth: the words and the rule live in
 * backend/app/agent/voice.py — nothing here decides them.
 */
import { apiUrl } from '@/lib/api'

let rule: { line: string; re: RegExp; cameraOff: string; trip: RegExp | null; tryLine: string; hello: string; helloBack: string; acks: string[] } | null = null
let loading: Promise<void> | null = null

export function loadFirstLine(): Promise<void> {
  if (rule || loading) return loading || Promise.resolve()
  loading = fetch(apiUrl('/api/agent/first-line'), { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : null))
    .then((j: { line?: string; work?: string; flags?: string; camera_off?: string; trip?: string; try?: string; hello?: string; hello_back?: string; acks?: string[] } | null) => {
      if (j?.line && j?.work) rule = { line: j.line, re: new RegExp(j.work, j.flags || 'i'), cameraOff: j.camera_off || '',
                                       trip: j.trip ? new RegExp(j.trip, j.flags || 'i') : null, tryLine: j.try || '',
                                       hello: j.hello || '', helloBack: j.hello_back || '', acks: Array.isArray(j.acks) ? j.acks.filter(x => typeof x === 'string' && x) : [] }
    })
    .catch(() => { /* not read: the stream's own first line still comes (~1 s) */ })
    .finally(() => { loading = null })
  return loading
}

/** Sasha 268 · her line when his request sends her back to the corner (voice.CAMERA_OFF), or '' when it hasn't been read. */
export function cameraOffLine(): string {
  return rule?.cameraOff || ''
}

/** Sasha 271 · B (row 1008) · her ARRIVAL in one breath (voice.arrival_line): "Hey there." — a return: "Hey <first name>." — then
 *  voice.CAMERA_OFF. Read once from the backend (waits for it); '' when it couldn't be read (she then just goes to the corner). */
export async function arrivalLine(name: string | null | undefined, back: boolean): Promise<string> {
  await loadFirstLine()
  if (!rule?.hello || !rule.cameraOff) return ''
  const first = String(name || '').trim().split(' ')[0].slice(0, 40)
  return `${back && first ? rule.helloBack.replace('{name}', first) : rule.hello}. ${rule.cameraOff}`
}

/** Sasha 273 · item 4 (c): her reappearance with NEWS leads with it — the news in its own words (the event's `say`, from the backend),
 *  then voice.CAMERA_OFF, exactly as her arrival. '' when the rule hasn't been read (she then just goes to the corner). */
export async function newsLine(news: string): Promise<string> {
  await loadFirstLine()
  const said = String(news || '').trim()
  if (!said || !rule?.cameraOff) return ''
  return `${/[.!?]$/.test(said) ? said : `${said}.`} ${rule.cameraOff}`
}

/** The first line for this message, when it is a request for work (and the rule has been read); else null. Sasha 268 · item 7: a
 *  trip, a table or dates → voice.FIRST_LINE; any other request for a service → voice.TRY_FIRST ("Let me see what I can do."). */
export function firstLineFor(text: string): string | null {
  if (!rule || !rule.re.test(text || '')) return null
  return !rule.tryLine || !rule.trip || rule.trip.test(text || '') ? rule.line : rule.tryLine
}

/** Sasha 273 · item 8 (row 1047): "Let me see what I can do" repeated on every turn of a booking. /s2's first line, by voice.py's ONE
 *  rule (voice.ack_for): the special line (the trip's / TRY_FIRST) at most ONCE per request, then the next line of voice.ACKS — never
 *  the same line twice in a row. The words are the backend's (GET /api/agent/first-line acks); the page only keeps what it said. A
 *  request is over after ACK_RESET_MS quiet or a New chat (forgetAcks). The stream is told what was said (said_first) and keeps it. */
const ACK_RESET_MS = 30 * 60 * 1000
let acked: { last: string | null; tried: Set<string>; at: number } = { last: null, tried: new Set(), at: 0 }

/** Is this message a request for work (no state touched)? */
export function isWork(text: string): boolean {
  return !!rule && rule.re.test(text || '')
}

/** The first line to say for this message now — and remembered as said; null when it isn't a request for work. */
export function takeFirstLine(text: string, now: number = Date.now()): string | null {
  const special = firstLineFor(text)
  if (!special || !rule) return null
  if (now - acked.at > ACK_RESET_MS) acked = { last: null, tried: new Set(), at: now }
  let line = special
  if (acked.tried.has(special) || acked.last === special) {
    const q = rule.acks
    if (!q.length) return null   // no quiver read: nothing rather than the same line again
    const i = acked.last && q.includes(acked.last) ? q.indexOf(acked.last) + 1 : 0
    line = q[i % q.length]
  }
  acked = { last: line, tried: new Set([...acked.tried, ...(line === special ? [special] : [])]), at: now }
  return line
}

/** New chat (or a new arrival): the next request may open with its first line again. */
export function forgetAcks(): void {
  acked = { last: null, tried: new Set(), at: 0 }
}
