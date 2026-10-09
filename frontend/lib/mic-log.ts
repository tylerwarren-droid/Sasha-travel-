/**
 * Sasha 213 · THE MIC'S STATE MACHINE, LOGGED — instrument first, no guessing. Every transition the mic goes through is
 * written here with its time: permission, the Deepgram key, the socket, speech start/end, partial and final transcripts,
 * what was dropped and why (echo, a repeat, muted while a turn runs, gated while she speaks), the gate opening and
 * closing, barge-in, re-arm, the AudioContext suspending. window.__micLog holds the last 2,000; `copy(window.__micLog)` in
 * the console takes them out; the /mic-test page reads them.
 */
export type MicEvent = { t: number; ev: string; [k: string]: unknown }

export function micLog(ev: string, data: Record<string, unknown> = {}): void {
  if (typeof window === 'undefined') return
  const w = window as unknown as { __micLog?: MicEvent[] }
  const log = (w.__micLog ??= [])
  log.push({ t: Math.round(performance.now()), ev, ...data })
  if (log.length > 2000) log.splice(0, log.length - 2000)
  if (ev !== 'partial') console.debug('[MIC]', ev, data)
}
