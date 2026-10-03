import type { Metadata } from 'next'
import { productsGet } from '@/lib/products'
import CopyAnswer from '../../campus-handover/[id]/CopyAnswer'

export const metadata: Metadata = { title: 'Your health appointment, prepared', robots: { index: false, follow: false } }
export const dynamic = 'force-dynamic'

/**
 * CR 4 · health, inside S-77's line. A SERMAS hand-over: the official appointment page, what it asks for (values only
 * from the vault or a FICTIONAL patient, shown for 24 hours), the appointment type, and "you press" — Kanoe never signs
 * in, books or presses on a public health website. Or the new-in-Madrid checklist, every step from its official page.
 */
type Step = { step: string; do: string; link: string; link_words?: string; source: string; how: string; note?: string }
type Case = {
  kind: 'sermas' | 'new_in_madrid'; appointment_type: string | null
  values: { card?: string; birth?: string; dni_nie?: string } | null; values_source: string | null; values_expire_at: string | null
  fictional: boolean; checklist: Step[] | null; reminders: { on: string; text: string; sent: boolean }[] | null
  sermas: { name: string; page: string; primary_care_url: string; app: string; phone: string; needs: string[]; not_valid: string; minors: string }
  read_on: string; expires_at: string
}

const at = (iso: string | null | undefined) => (iso ? new Date(iso).toUTCString().replace(' GMT', ' UTC') : '—')
const born = (iso?: string) => (iso ? new Date(`${iso}T12:00:00Z`).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' }) : '')

function Value({ label, value }: { label: string; value?: string }) {
  return (
    <li className="rounded border border-emerald-200 bg-emerald-50 p-3">
      <div className="text-sm font-medium">{label}</div>
      {value ? (
        <div className="mt-1 font-mono text-base">{value}<CopyAnswer text={value} /></div>
      ) : (
        <div className="mt-1 text-sm text-slate-600">Have it ready — it’s on your card. Kanoe doesn’t hold it.</div>
      )}
    </li>
  )
}

export default async function HealthHandover({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const r = await productsGet<Case>(`/health/${encodeURIComponent(id)}`)
  if (!r.ok) {
    return <main className="min-h-screen bg-white"><div className="mx-auto max-w-2xl px-4 py-12 text-slate-800"><h1 className="text-xl font-semibold">Health</h1><p className="mt-4">{r.message}</p></div></main>
  }
  const c = r.data
  const s = c.sermas
  return (
    <main className="min-h-screen bg-white">
      <div className="mx-auto max-w-2xl px-4 py-8 text-slate-800">
        {c.fictional && (
          <p className="mb-4 rounded border border-violet-300 bg-violet-50 p-3 text-sm">Illustration: the patient shown here is fictional. The pages and links are the real official ones.</p>
        )}
        {c.kind === 'sermas' ? (
          <>
            <p className="text-sm font-medium uppercase tracking-wide text-slate-500">Prepared · you book it</p>
            <h1 className="mt-1 text-2xl font-semibold">Your appointment with the public health service (SERMAS)</h1>
            <p className="mt-1 text-slate-600">{c.appointment_type}</p>
            <section className="mt-6 rounded-lg border border-slate-300 p-4">
              <p className="font-medium">Kanoe prepares this; you press.</p>
              <p className="mt-1 text-sm text-slate-600">Open SERMAS’s own page, enter what it asks for, and choose your appointment. Kanoe never signs in, books or presses on a public health website, and never searches for free slots for you.</p>
              <a href={s.primary_care_url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block rounded bg-slate-900 px-4 py-2 text-white">Open SERMAS — Atención Primaria ↗</a>
              <p className="mt-3 text-xs text-slate-500">Or {s.app}, or by phone: {s.phone}.</p>
            </section>
            <h2 className="mt-6 text-base font-semibold">What SERMAS asks for</h2>
            <ol className="mt-2 space-y-2">
              <Value label="The code of your tarjeta sanitaria" value={c.values?.card} />
              <Value label="Your date of birth" value={born(c.values?.birth)} />
              <Value label="Your DNI or NIE" value={c.values?.dni_nie} />
            </ol>
            <p className="mt-2 text-sm text-slate-700">“{s.not_valid}” — a passport number isn’t accepted. For under-16s: {s.minors}.</p>
            {c.values && (
              <p className="mt-2 text-xs text-slate-500">From {c.values_source}. Shown until {at(c.values_expire_at)}, then removed from this page.</p>
            )}
          </>
        ) : (
          <>
            <p className="text-sm font-medium uppercase tracking-wide text-slate-500">New in Madrid · step by step</p>
            <h1 className="mt-1 text-2xl font-semibold">Your health card and your family doctor</h1>
            <ol className="mt-6 space-y-3">
              {(c.checklist ?? []).map((x) => (
                <li key={x.step} className="rounded border border-slate-300 p-4">
                  <div className="font-medium">{x.step}</div>
                  <p className="mt-1 text-sm">{x.do}</p>
                  {x.note && <p className="mt-1 text-sm text-slate-700">{x.note}</p>}
                  <a href={x.link} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-sm underline">{x.link_words ?? 'The official page'} ↗</a>
                  <p className="mt-1 text-xs text-slate-500">Source: {x.source} ({x.how === '● raw' ? 'read at source' : 'read through the official site'}), {c.read_on}.</p>
                </li>
              ))}
            </ol>
            <p className="mt-3 text-sm text-slate-700">You make each appointment yourself. Kanoe never hunts for padrón or health appointments — they’re scarce, and automated searching takes them from other people.</p>
            {c.reminders && c.reminders.length > 0 && (
              <ul className="mt-3 space-y-0.5 text-xs text-slate-700">
                {c.reminders.map((x) => <li key={x.on}>⏰ {new Date(`${x.on}T12:00:00Z`).toUTCString().slice(5, 16)}: {x.text}{x.sent ? ' (sent)' : ''}</li>)}
              </ul>
            )}
          </>
        )}
        <p className="mt-10 text-xs text-slate-500">
          Health details: only what this needs; never why you need a doctor; deleted after 30 days ({at(c.expires_at)}). Pages read {c.read_on}.
          Kanoe Technologies SL · Calle Padre Damián 41, 28036 Madrid.
        </p>
      </div>
    </main>
  )
}
