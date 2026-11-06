/**
 * Sasha 347 · THE ONE OUTCOME PATH on the page (346's heard(), moved here so every page that acts uses the same one — /group, S2, the
 * booking pages). The server decides what was done or exactly why not (booking_signer/group_outcome.py and every route's `say`); this
 * reads it, and says what happened to the request when the server couldn't. Nothing here is ever empty, and nothing is greyed out:
 *
 *   heard(name, res)      a response → the words to show (the server's say / why / message, else what happened to the request)
 *   failed(name, error)   a request or step that threw → the words to show
 *   needs(name, fields)   an action pressed without what it needs → "Send needs a message." (the fields by their names on the page)
 *   stillGoing(run, name) a press while something else runs → told, never ignored
 *   again(title)          a card's choice pressed after it was answered → told, nothing sent twice
 *   observe(p, name, tell) every promise a page starts: its failure is TOLD (to the person, or — for a step that is not theirs, such as a
 *                         timing beacon — to the console with its name), never dropped
 */

export type Res = { ok: boolean; status: number; json: Record<string, unknown> } | null

const and = (xs: string[]) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`)

export function words(j: unknown): string {
  const o = (j && typeof j === 'object' ? j : {}) as Record<string, unknown>
  return String(o.say || o.why || o.message || '').trim()
}

export function heard(name: string, r: Res): string {
  return words(r?.json) || (!r ? `${name}: Sasha’s server didn’t answer — nothing was changed. Try again.`
    : `${name}: the server answered ${r.status} without words — nothing was changed. Try again.`)
}

/** a browser's words for "the network is gone" (Chrome · Safari · Firefox) */
const CHUNK = /failed to load chunk|loading chunk [\w-]+ failed|chunkloaderror|importing a module script failed|error loading dynamically imported module/i
const OFFLINE = /failed to fetch|load failed|networkerror|network request failed|err_internet_disconnected|could(n’t|n't| not) be reached/i

export function failed(name: string, e: unknown): string {
  const why = e instanceof Error && e.message ? e.message : typeof e === 'string' ? e : ''
  if (OFFLINE.test(why) || (typeof navigator !== 'undefined' && navigator.onLine === false))   // Sasha 348 · the connection, said plainly
    return `${name} couldn’t reach Sasha — your connection seems to be off. Try again when it’s back.`
  if (CHUNK.test(why))   // Sasha 348 · a piece of the page that failed to load (while offline) stays failed until the page loads again
    return `${name} couldn’t load part of this page — reload the page and try again.`
  return `${name} didn’t go through${why ? ` (${why})` : ''} — nothing was changed. Try again.`
}

export const needs = (name: string, fields: string[]) => `${name} needs ${and(fields)}.`

export const stillGoing = (running: string, pressed: string) => `${running} is still going — press ${pressed} again once it has answered.`

export const again = (title: string) => `Already answered — “${title}”. Nothing more was sent.`

/** a step that is not the person's (a timing beacon, her greeting's sound): its failure goes to the console, named — never dropped */
export const toConsole = (said: string) => console.warn(`[outcome] ${said}`)

export function observe<T>(p: Promise<T> | null | undefined, name: string, tell: (said: string) => void): void {
  if (p) p.catch((e: unknown) => tell(failed(name, e)))   // nothing started (an optional step that wasn't there): nothing to tell
}

/** Sasha 348 · a catch's own teller for a step that isn't the person's (a browser capability, a background read): `.catch(noted('…'))`,
 *  `catch (e) { noted('…')(e) }` — the failure is named in the console, never swallowed. */
export const noted = (name: string) => (e: unknown): void => toConsole(failed(name, e))

/** Sasha 348 · THE page's one line to a person when a page has no message place of its own: a polite live region (role=status), shown for
 *  a few seconds. A page with its own place to say things uses that instead. */
export function announce(text: string): void {
  if (typeof document === 'undefined') { toConsole(text); return }
  let el = document.getElementById('sasha-outcome') as (HTMLDivElement & { _t?: ReturnType<typeof setTimeout> }) | null
  if (!el) {
    el = document.createElement('div')
    el.id = 'sasha-outcome'
    el.setAttribute('role', 'status')
    el.setAttribute('aria-live', 'polite')
    Object.assign(el.style, { position: 'fixed', left: '50%', top: '12px', transform: 'translateX(-50%)', maxWidth: 'min(92vw, 520px)',
      padding: '10px 14px', borderRadius: '12px', background: 'rgba(20,20,28,.96)', color: '#fff', border: '1px solid rgba(255,255,255,.18)',
      font: '14px/1.4 system-ui, sans-serif', zIndex: '2147483647', boxShadow: '0 6px 24px rgba(0,0,0,.45)' })
    document.body.appendChild(el)
  }
  el.textContent = text
  el.style.display = 'block'
  if (el._t) clearTimeout(el._t)
  el._t = setTimeout(() => { if (el) el.style.display = 'none' }, 7000)
}
