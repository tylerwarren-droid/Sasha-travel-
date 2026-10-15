/**
 * Sasha 265 · item 5 (row 935, Tyler: "an IMMEDIATE first line, under 1 s") — voice.first_line, read from the backend ONCE
 * (GET /api/agent/first-line: its words and its rule for a request for work). The page says it the instant such a request is sent;
 * the stream's own first line (`first: true`) is the same words and is then not said twice. One truth: the words and the rule live in
 * backend/app/agent/voice.py — nothing here decides them.
 */
import { apiUrl } from '@/lib/api'

let rule: { line: string; re: RegExp; cameraOff: string; trip: RegExp | null; tryLine: string; hello: string; helloBack: string } | null = null
let loading: Promise<void> | null = null

export function loadFirstLine(): Promise<void> {
  if (rule || loading) return loading || Promise.resolve()
  loading = fetch(apiUrl('/api/agent/first-line'), { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : null))
    .then((j: { line?: string; work?: string; flags?: string; camera_off?: string; trip?: string; try?: string; hello?: string; hello_back?: string } | null) => {
      if (j?.line && j?.work) rule = { line: j.line, re: new RegExp(j.work, j.flags || 'i'), cameraOff: j.camera_off || '',
                                       trip: j.trip ? new RegExp(j.trip, j.flags || 'i') : null, tryLine: j.try || '',
                                       hello: j.hello || '', helloBack: j.hello_back || '' }
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

/** The first line for this message, when it is a request for work (and the rule has been read); else null. Sasha 268 · item 7: a
 *  trip, a table or dates → voice.FIRST_LINE; any other request for a service → voice.TRY_FIRST ("Let me see what I can do."). */
export function firstLineFor(text: string): string | null {
  if (!rule || !rule.re.test(text || '')) return null
  return !rule.tryLine || !rule.trip || rule.trip.test(text || '') ? rule.line : rule.tryLine
}
