'use client'

import { useState } from 'react'

/**
 * CR 8 · "Return to applicant with this list". Every outcome is shown: recorded (with the exact message), or why not.
 * In this click-through nothing is sent — the page says so.
 */
export default function ReturnButton({ caseId, appId, message, already }: { caseId: string; appId: string; message: string; already: string | null }) {
  const [state, setState] = useState<{ kind: 'idle' | 'busy' | 'done' | 'failed'; at?: string; why?: string }>(
    already ? { kind: 'done', at: already } : { kind: 'idle' })
  const [show, setShow] = useState(false)
  const send = async () => {
    setState({ kind: 'busy' })
    try {
      const r = await fetch(`/api/products/relocation/officer/${encodeURIComponent(caseId)}/return/${encodeURIComponent(appId)}`, { method: 'POST' })
      const j = await r.json()
      if (!r.ok) {
        setState({ kind: 'failed', why: (j && j.message) || `HTTP ${r.status}` })
        return
      }
      setState({ kind: 'done', at: j.returned?.at })
      setShow(true)
    } catch (e) {
      setState({ kind: 'failed', why: (e as Error).message })
    }
  }
  return (
    <div className="mt-3">
      {state.kind === 'done' ? (
        <p className="text-sm text-emerald-800">↩ Returned to the applicant with this list{state.at ? ` (${new Date(state.at).toUTCString().replace(' GMT', ' UTC')})` : ''}. Illustration: recorded only — nothing was sent.</p>
      ) : (
        <button type="button" onClick={send} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700">
          {state.kind === 'busy' ? 'Returning…' : 'Return to applicant with this list'}
        </button>
      )}
      {state.kind === 'failed' && <p className="mt-1 text-sm text-rose-700">Not returned: {state.why}</p>}
      <button type="button" onClick={() => setShow((v) => !v)} className="ml-3 text-sm underline">{show ? 'Hide the message' : 'See the message'}</button>
      {show && <pre className="mt-2 whitespace-pre-wrap rounded border border-slate-200 bg-slate-50 p-3 text-xs">{message}</pre>}
    </div>
  )
}
