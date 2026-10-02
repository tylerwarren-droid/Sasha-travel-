'use client'

/**
 * S-80 · AN INVITATION — "Ana invited you to dinner": pick a time. No account, no sign-in.
 *
 * Shows only what the invited guest may see: the inviter's first name, the activity, the times, and the outcome. Picking
 * a time shares only that choice; the booking stays the inviter's. Sasha messages them on WhatsApp only if they ask.
 */
import { use, useEffect, useState } from 'react'

type Slot = { words: string; start: string; end: string }
type View = { inviter: string; invitee: string | null; activity: string; slots: Slot[]; chosen: number | null; status: string
  consent: string; consent_sha256: string; whatsapp: string | null; booked?: { venue: string; day: string; time: string } }

export default function InvitePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params)
  const [view, setView] = useState<View | null>(null)
  const [words, setWords] = useState<string | null>(null)
  const [pick, setPick] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [ticked, setTicked] = useState(false)

  useEffect(() => {
    let off = false
    fetch(`/api/invite/${encodeURIComponent(code)}`).then(async (r) => {
      const j = await r.json().catch(() => ({}))
      if (off) return
      if (r.ok) { setView(j as View); setName((j as View).invitee ?? '') } else setWords(String((j as { message?: string }).message ?? 'This invitation could not be opened.'))
    }).catch((e) => { if (!off) setWords((e as Error).message) })
    return () => { off = true }
  }, [code])

  async function send(body: Record<string, unknown>) {
    if (!view) return
    const r = await fetch(`/api/invite/${encodeURIComponent(code)}/choose`, { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ ...body, consent_sha256: view.consent_sha256 }) })
    const j = await r.json().catch(() => ({})) as { say?: string; message?: string; status?: string }
    setWords(r.ok ? (j.say ?? 'Sent.') : (j.message ?? 'That didn’t go through.'))
    if (r.ok) setView({ ...view, status: j.status ?? view.status, chosen: typeof body.slot === 'number' ? body.slot : view.chosen })
  }

  return (
    <main className="mx-auto my-8 max-w-md space-y-4 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
      {!view && <p>{words ?? 'Opening the invitation…'}</p>}
      {view && (
        <>
          <h1 className="text-xl font-semibold">{view.inviter} invited you to {view.activity}</h1>
          {view.booked && <p className="rounded bg-green-50 p-2"><strong>Booked:</strong> {view.booked.venue}, {view.booked.day} at {view.booked.time} — under {view.inviter}&rsquo;s name.</p>}
          {view.status === 'expired' && <p>This invitation has expired.</p>}
          {view.status === 'cancelled' && <p>{view.inviter} cancelled the {view.activity}.</p>}
          {view.status === 'chosen' && view.chosen !== null && !view.booked && <p>You picked <strong>{view.slots[view.chosen]?.words}</strong>. {view.inviter} will book it; it shows here once it&rsquo;s booked.</p>}
          {view.status === 'open' && (
            <div className="space-y-3">
              <p>Pick a time that suits you:</p>
              <ul className="space-y-1">
                {view.slots.map((s, i) => (
                  <li key={i}><label className="flex items-center gap-2"><input type="radio" name="slot" checked={pick === i} onChange={() => setPick(i)} /> {s.words}</label></li>
                ))}
              </ul>
              <input className="w-full rounded border px-2 py-1" placeholder="Your first name" value={name} onChange={(e) => setName(e.target.value)} />
              <label className="flex items-start gap-2"><input type="checkbox" checked={ticked} onChange={(e) => setTicked(e.target.checked)} /><span>{view.consent}</span></label>
              <div className="flex gap-2">
                <button type="button" className="rounded border px-3 py-1" onClick={() => { if (pick !== null && ticked) send({ slot: pick, first_name: name }) }}>
                  {pick === null ? 'Pick a time first' : !ticked ? 'Tick the sentence first' : 'Send my choice'}</button>
                <button type="button" className="rounded border px-3 py-1" onClick={() => { if (ticked) send({ none: true }) }}>
                  {ticked ? 'None of these work' : 'Tick the sentence to say none work'}</button>
              </div>
            </div>
          )}
          {words && <p>{words}</p>}
          {view.whatsapp && view.status !== 'expired' && (
            <p className="text-xs opacity-75">Want Sasha to tell you on WhatsApp when it&rsquo;s booked? <a className="underline" href={view.whatsapp} target="_blank" rel="noopener noreferrer">Send her a message</a> — about this {view.activity} only.</p>
          )}
        </>
      )}
    </main>
  )
}
