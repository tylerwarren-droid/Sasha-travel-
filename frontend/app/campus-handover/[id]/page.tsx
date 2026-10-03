import type { Metadata } from 'next'
import { productsGet } from '@/lib/products'
import CopyAnswer from './CopyAnswer'

export const metadata: Metadata = { title: 'CampusMe · your registration, prepared', robots: { index: false, follow: false } }
export const dynamic = 'force-dynamic'

/**
 * CR 1 · CampusMe's hand-over: the school's OWN registration form, question by question — what to enter and where it
 * came from — then the parent opens the school's page and presses Register. ⛔ This page submits nothing and links to
 * no submit; a statement or consent on the form is always marked as theirs to tick.
 */
type Row = { label: string; required: boolean; action: 'fill' | 'choose' | 'you' | 'skip' | 'not_you'; answer: string | null; source: string | null; note: string | null }
type Case = {
  school: { name: string; full_name: string; city: string; host: string; rules: string[] }
  session: { day: string; start: string; end: string | null; title: string; location: string | null; spaces: number | null; read: { at: string; sha256: string } }
  form_url: string; form_read: { at: string; sha256: string } | null; form_pages: number; challenge_seen: boolean
  rows: Row[]; counts: Record<string, number>; status: string; confirmation_quote: string | null; expires_at: string
  fictional: boolean
}

const STYLE: Record<Row['action'], { box: string; tag: string }> = {
  fill: { box: 'border-emerald-200 bg-emerald-50', tag: 'Enter' },
  choose: { box: 'border-sky-200 bg-sky-50', tag: 'Choose' },
  you: { box: 'border-amber-300 bg-amber-50', tag: 'Yours to answer' },
  skip: { box: 'border-slate-200 bg-white', tag: 'Optional' },
  not_you: { box: 'border-slate-200 bg-slate-50 opacity-70', tag: 'Not for you' },
}

const when = (day: string, start: string) => {
  const [h, m] = start.split(':').map(Number)
  const d = new Date(`${day}T12:00:00Z`).toLocaleDateString('en-US', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
  return `${d}, ${(h % 12) || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}
const at = (iso: string | undefined) => (iso ? new Date(iso).toUTCString().replace(' GMT', ' UTC') : '—')

export default async function CampusHandover({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const r = await productsGet<Case>(`/campus/${encodeURIComponent(id)}`)
  if (!r.ok) {
    return (
      <main className="min-h-screen bg-white"><div className="mx-auto max-w-2xl px-4 py-12 text-slate-800">
        <h1 className="text-xl font-semibold">CampusMe</h1>
        <p className="mt-4">{r.message}</p>
      </div></main>
    )
  }
  const c = r.data
  const s = c.session
  const filled = (c.counts.fill ?? 0) + (c.counts.choose ?? 0)
  const yours = c.counts.you ?? 0
  return (
    <main className="min-h-screen bg-white"><div className="mx-auto max-w-2xl px-4 py-8 text-slate-800">
      {c.fictional && (
        <p className="mb-4 rounded border border-violet-300 bg-violet-50 p-3 text-sm">Illustration: the student shown here is fictional. The session and the form are the school’s real ones, read live; nothing was sent to the school.</p>
      )}
      <p className="text-sm font-medium uppercase tracking-wide text-slate-500">CampusMe · prepared, not sent</p>
      <h1 className="mt-1 text-2xl font-semibold">{c.school.full_name}: {s.title.split(' · ')[0]}</h1>
      <p className="mt-1 text-slate-600">{when(s.day, s.start)} ({c.school.city} time){s.location ? ` · ${s.location}` : ''}</p>
      {c.status === 'confirmed_in_writing' && c.confirmation_quote && (
        <p className="mt-3 rounded border border-emerald-300 bg-emerald-50 p-3 text-sm">✅ Confirmed in {c.school.name}’s own words: “{c.confirmation_quote}”</p>
      )}
      {c.status === 'registered_on_your_word' && (
        <p className="mt-3 rounded border border-sky-300 bg-sky-50 p-3 text-sm">Registered on your word. It counts as confirmed when {c.school.name}’s own email says so — paste it to CampusMe on WhatsApp.</p>
      )}

      <section className="mt-6 rounded-lg border border-slate-300 p-4">
        <p className="font-medium">CampusMe prepares this registration; it doesn’t send it.</p>
        <p className="mt-1 text-sm text-slate-600">
          {filled} answer{filled === 1 ? '' : 's'} below come from your student’s details; {yours} {yours === 1 ? 'is' : 'are'} yours to answer or tick yourself.
          Open {c.school.name}’s page, enter them, check everything, and press Register there.
        </p>
        <a href={c.form_url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block rounded bg-slate-900 px-4 py-2 text-white">
          Open {c.school.name}’s registration page ↗
        </a>
        <ul className="mt-3 list-disc pl-5 text-xs text-slate-500">
          {c.form_pages > 1 && <li>The form has {c.form_pages} pages. This lists page 1; page 2 appears after you continue, and CampusMe hasn’t read it.</li>}
          <li>{c.challenge_seen ? 'The page carries a CAPTCHA: that’s yours to answer.' : 'No CAPTCHA was seen when the page was read; parts of it load as you go, so one may still appear.'}</li>
          <li>Session read from {c.school.host} at {at(s.read?.at)}{s.spaces != null ? `, ${s.spaces} spaces left then` : ''}. Spaces change.</li>
          <li>The school’s own words: {c.school.rules.join(' ')}</li>
        </ul>
      </section>

      <ol className="mt-6 space-y-2">
        {c.rows.map((row, i) => (
          <li key={i} className={`rounded border p-3 ${STYLE[row.action].box}`}>
            <div className="flex items-start justify-between gap-3">
              <span className="text-sm font-medium">{row.label}{row.required ? ' *' : ''}</span>
              <span className="shrink-0 text-xs uppercase tracking-wide text-slate-500">{STYLE[row.action].tag}</span>
            </div>
            {row.answer && (
              <div className="mt-1 text-base">
                <span className="font-mono">{row.answer}</span>
                <CopyAnswer text={row.answer} />
              </div>
            )}
            {row.source && <div className="mt-0.5 text-xs text-slate-500">from: {row.source}</div>}
            {row.note && <div className="mt-0.5 text-xs text-slate-600">{row.note}</div>}
          </li>
        ))}
      </ol>

      <p className="mt-8 text-xs text-slate-500">
        Form read from {c.school.host} at {at(c.form_read?.at ?? undefined)} (sha256 {c.form_read?.sha256.slice(0, 12)}…). This page expires {at(c.expires_at)}.
        CampusMe by Kanoe Technologies SL · Calle Padre Damián 41, 28036 Madrid.
      </p>
    </div></main>
  )
}
