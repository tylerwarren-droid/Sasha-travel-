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

export function failed(name: string, e: unknown): string {
  const why = e instanceof Error && e.message ? e.message : ''
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
