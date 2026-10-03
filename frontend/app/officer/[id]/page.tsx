import type { Metadata } from 'next'
import { productsGet } from '@/lib/products'
import ReturnButton from './ReturnButton'

export const metadata: Metadata = { title: 'Case officer — EX-01 queue (illustration)', robots: { index: false, follow: false } }
export const dynamic = 'force-dynamic'

/**
 * CR 8 · what an administration, an NGO or a law firm would see: five FICTIONAL EX-01 applications, each run through the
 * same form checks and consulate checklist a real file is, sorted by what needs attention. CLICK-THROUGH: the people are
 * invented; the checks are real; "return" records the message — nothing is sent. No percentages: counts of open items.
 */
type Item = { level: 'problem' | 'missing' | 'check'; field: string; why: string; from: string }
type App = {
  id: string; name: string; nationality: string; received: string; status: 'return' | 'check' | 'complete'
  counts: { problem: number; missing: number; check: number }; open_items: number; items: Item[]
  left_for_applicant: number; filled: number; returned: { at: string } | null; message: string
}

const STATUS: Record<App['status'], { label: string; cls: string }> = {
  return: { label: 'Needs to go back to the applicant', cls: 'border-rose-300 bg-rose-50' },
  check: { label: 'A point to check', cls: 'border-amber-300 bg-amber-50' },
  complete: { label: 'Complete — awaiting the applicant’s signature', cls: 'border-emerald-300 bg-emerald-50' },
}
const LEVEL: Record<Item['level'], string> = { problem: '✗', missing: '＋', check: '△' }

export default async function Officer({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const r = await productsGet<{ applications: App[] }>(`/relocation/officer/${encodeURIComponent(id)}`)
  if (!r.ok) {
    return <main className="min-h-screen bg-white"><div className="mx-auto max-w-3xl px-4 py-12 text-slate-800"><h1 className="text-xl font-semibold">Case officer</h1><p className="mt-4">{r.message}</p></div></main>
  }
  const apps = r.data.applications
  const open = apps.filter((a) => a.status !== 'complete').length
  return (
    <main className="min-h-screen bg-white">
      <div className="mx-auto max-w-3xl px-4 py-8 text-slate-800">
        <p className="mb-4 rounded border border-violet-300 bg-violet-50 p-3 text-sm"><b>CLICK-THROUGH.</b> Illustration: a scripted walk through a real flow. Names and data are fictional. The form, its checks and the consulate’s checklist are the real ones; “return” records the message and sends nothing.</p>
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">Case officer · EX-01 · residencia no lucrativa</p>
        <h1 className="mt-1 text-2xl font-semibold">{apps.length} applications — {open} need attention before they’re assessed</h1>
        <p className="mt-1 text-sm text-slate-600">Most attention first: problems, then missing documents, then points to check. Each line is the check’s own words. All five apply at the Spanish Consulate General in London, whose own checklist (dated 11 Feb 2022) the documents are checked against.</p>
        <ol className="mt-6 space-y-4">
          {apps.map((a) => (
            <li key={a.id} className={`rounded-lg border p-4 ${STATUS[a.status].cls}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{a.name} <span className="text-xs font-normal text-slate-500">{a.id} · {a.nationality} · received {a.received}</span></div>
                  <div className="text-sm">{STATUS[a.status].label}</div>
                </div>
                <div className="shrink-0 text-right text-xs text-slate-600">
                  <div><b>{a.counts.problem}</b> problem{a.counts.problem === 1 ? '' : 's'}</div>
                  <div><b>{a.counts.missing}</b> missing document{a.counts.missing === 1 ? '' : 's'}</div>
                  <div><b>{a.counts.check}</b> to check</div>
                </div>
              </div>
              {a.items.length > 0 && (
                <ul className="mt-3 space-y-1 text-sm">
                  {a.items.map((i, k) => <li key={k}><span className="mr-1">{LEVEL[i.level]}</span><b>{i.field}:</b> {i.why} <span className="text-xs text-slate-500">— {i.from}</span></li>)}
                </ul>
              )}
              <p className="mt-2 text-xs text-slate-600">{a.filled} boxes filled from the applicant’s documents; {a.left_for_applicant} left for the applicant (section 5, the Dehú consent, the signature) — expected, not a fault.</p>
              {a.status !== 'complete' && <ReturnButton caseId={id} appId={a.id} message={a.message} already={a.returned?.at ?? null} />}
            </li>
          ))}
        </ol>
        <p className="mt-10 text-xs text-slate-500">Kanoe Technologies SL · Calle Padre Damián 41, 28036 Madrid.</p>
      </div>
    </main>
  )
}
