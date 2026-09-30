'use client'

/**
 * S-55 · The emailed link's two pages: CONFIRM (the double opt-in) and WITHDRAW.
 *
 * ⛔ Opening the link writes nothing — mail scanners open links on their own. The page shows what would be recorded
 * (POST preview, which writes nothing), and only the button writes: Confirm → one venue_optins row per channel;
 * Withdraw → a withdrawal for every channel of the venue, which stops phone and email too (optins.py).
 */
import { useEffect, useState } from 'react'
import { COPY, call, type Channel, type Lang } from './copy'

type Req = { venue_name: string; contact_name: string; contact_role: string; email: string; expires_at: string
  confirmed_at: string | null; withdrawn_at: string | null; channels: Array<{ channel: Channel; scope: string; wording_text: string }> }
type Phase = { phase: 'loading' } | { phase: 'shown'; req: Req } | { phase: 'working'; req: Req }
  | { phase: 'done'; req: Req; words: string } | { phase: 'refused'; req?: Req; message: string }

/** "30 SEP 2026, 14:05" — a real date, never a relative one */
const when = (iso: string) => {
  const d = new Date(iso)
  const day = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase()
  return `${day}, ${d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`
}

export default function LinkAction({ mode, token, lang }: { mode: 'confirm' | 'withdraw'; token: string; lang: Lang }) {
  const t = COPY[lang]
  const [p, setP] = useState<Phase>({ phase: 'loading' })

  useEffect(() => {
    let off = false
    ;(async () => {
      try {
        const r = await call('preview', { t: token })
        if (off) return
        if (!r.ok) { setP({ phase: 'refused', message: String(r.json.message ?? r.json.rule ?? `HTTP ${r.status}`) }); return }
        setP({ phase: 'shown', req: r.json.request as Req })
      } catch {
        if (!off) setP({ phase: 'refused', message: t.unreachable })
      }
    })()
    return () => { off = true }
  }, [token, t.unreachable])

  async function act(req: Req) {
    setP({ phase: 'working', req })
    try {
      const r = await call(mode, { t: token })
      if (!r.ok) { setP({ phase: 'refused', req, message: String(r.json.message ?? r.json.rule ?? `HTTP ${r.status}`) }); return }
      const words = mode === 'withdraw' ? t.withdrawn(req.venue_name) : r.json.status === 'already_confirmed' ? t.alreadyConfirmed : t.confirmed
      setP({ phase: 'done', req: r.json.request as Req, words })
    } catch (e) {
      setP({ phase: 'refused', req, message: (e as Error).message })
    }
  }

  const req = p.phase === 'loading' ? null : p.req ?? null
  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-10 text-[15px] leading-relaxed">
      <h1 className="text-2xl font-semibold">{mode === 'confirm' ? t.confirmTitle : t.withdrawTitle} {req?.venue_name ?? ''}</h1>
      {p.phase === 'loading' && <p className="mt-6 text-sm">{t.loading}</p>}

      {req && (
        <div className="mt-6 space-y-4">
          <p className="text-sm">{t.agreedBy(req.contact_name, req.contact_role, req.email)}</p>
          {mode === 'withdraw' && <p className="font-medium">{t.withdrawIntro}</p>}
          <ul className="space-y-3">
            {req.channels.map((c) => (
              <li key={c.channel} className="rounded border p-3">
                <p className="font-medium">{t.channel[c.channel]} · {c.scope}</p>
                <blockquote className="mt-1 border-l-2 pl-3 text-sm italic">{c.wording_text}</blockquote>
              </li>
            ))}
          </ul>
          {mode === 'confirm' && req.confirmed_at && <p className="text-sm">✓ {when(req.confirmed_at)}</p>}
          {req.withdrawn_at && <p className="text-sm">✕ {when(req.withdrawn_at)}</p>}
        </div>
      )}

      {(p.phase === 'shown' || p.phase === 'working') && (
        <button type="button" disabled={p.phase === 'working'} onClick={() => void act(p.req)}
          className={`mt-6 rounded px-4 py-2 text-white disabled:opacity-40 ${mode === 'withdraw' ? 'bg-red-800' : 'bg-black'}`}>
          {mode === 'confirm' ? t.confirmBtn : t.withdrawBtn}
        </button>
      )}
      {p.phase === 'done' && <p className="mt-6 rounded bg-black/5 p-3 font-medium">{p.words}</p>}
      {p.phase === 'refused' && <p className="mt-6 text-sm text-red-800">{t.link} {p.message}</p>}

      <p className="mt-10 text-sm"><a className="underline" href={`/work-with-sasha?lang=${lang}`}>{t.back}</a></p>
      <p className="mt-6 text-xs opacity-70">{t.operated}</p>
    </main>
  )
}
