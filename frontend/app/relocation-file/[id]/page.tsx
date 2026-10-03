import type { Metadata } from 'next'
import { productsGet } from '@/lib/products'

export const metadata: Metadata = { title: 'Your EX-01 · prepared, not signed, not filed', robots: { index: false, follow: false } }
export const dynamic = 'force-dynamic'

/**
 * CR 1 · the relocation reviewer's screen (AD P807lu's design, built here for a real file): every one of the EX-01's 96
 * widgets in reading order, its state, where its value came from, and what the reviewer agent checked.
 * ⛔ Each blank kind has its OWN style (P807lu §2.1) · no percentage or ratio anywhere (§2.5) · never "submitted",
 * "certified", or a time figure (§5) · the signature box is drawn as left for the applicant, not signed.
 */
type Check = { level: 'ok' | 'check' | 'problem'; why: string }
type Row = {
  name: string; page: number; type: string; section: string; label: string; measured_label: string | null
  state: 'filled' | 'answered_by_sibling' | 'prepared_not_adopted' | 'blank_no_data' | 'blank_no_mapping' | 'blank_unplaced' | 'not_applicable'
  value: string | null; provenance: string | null; why: string | null; the_person_must?: string; kind?: string
  checks: Check[]; verdict: Check['level'] | null
}
type File = {
  rows: Row[]; counts: Record<Row['state'], number>; checks: Record<Check['level'], number>; status: string; route: string | null
  fictional: boolean; prepared_at: string; signed_at: string | null; expires_at: string
  after: null | {
    residence?: string; entry_date?: string
    state?: string; county?: string
    consulate?: null | {
      id?: string; office: string; appointment_url: string | null; appointment_words: string; one_per_person: string
      appointment_email?: string | null; general?: string | null
      territory?: { from?: string; dated?: string | null; url?: string | null; states?: string[] }
      source: { name: string; url: string; dated: string; read: string }
    }
    consulate_unreadable?: { office: string; why: string }
    checklist?: { key: string; n?: number; label?: string | null; words: string; source: string; copies?: string | null; placeholder?: string | null; status: 'yours' | 'ok' | 'problem' | 'prepared' | 'not_needed'; why: string | null }[]
    email_draft?: { to: string; subject: string; body: string; attach: string[]; mailto: string } | null
    pack?: { n: number; name: string; title: string; status: 'gathered' | 'missing' | 'prepared'; copies: string | null }[]
    reminders?: { on: string; text: string; sent: boolean }[]
  }
  form: { name: string; title: string; pages: number; widgets: number; pdf_sha256: string }
}

const STATE: Record<Row['state'], { cls: string; chip: string }> = {
  filled: { cls: 'rf-filled border-emerald-300 bg-emerald-50', chip: '✓ filled' },
  answered_by_sibling: { cls: 'rf-sibling border-emerald-100 bg-white', chip: 'answered on this row' },
  prepared_not_adopted: { cls: 'rf-prepared border-2 border-amber-500 bg-amber-50', chip: '⚠ yours to make' },
  blank_no_data: { cls: 'rf-nodata border-dashed border-slate-400 bg-white', chip: '○ blank — no data' },
  blank_no_mapping: { cls: 'rf-nomapping border-dotted border-slate-500 bg-slate-50', chip: '◍ blank — no mapping' },
  blank_unplaced: { cls: 'rf-unplaced border-double border-4 border-rose-300 bg-rose-50', chip: '⚠ blank — unplaced' },
  not_applicable: { cls: 'rf-na border-slate-200 bg-slate-100 text-slate-500', chip: '— not your case' },
}
const VERDICT: Record<Check['level'], string> = { ok: 'text-emerald-700', check: 'text-amber-700', problem: 'text-rose-700 font-semibold' }
const at = (iso: string | null | undefined) => (iso ? new Date(iso).toUTCString().replace(' GMT', ' UTC') : '—')

function RowView({ r }: { r: Row }) {
  const s = STATE[r.state]
  return (
    <li className={`rounded border p-3 ${s.cls}`}>
      <div className="flex items-start justify-between gap-3">
        <span className="text-sm"><span className="font-medium">{r.label}</span> <span className="text-xs text-slate-400">{r.name} · p{r.page}</span></span>
        <span className="shrink-0 text-xs uppercase tracking-wide text-slate-600">{s.chip}</span>
      </div>
      {r.state === 'prepared_not_adopted' ? (
        <div className="mt-2 rounded border-2 border-dashed border-amber-600 p-3 text-sm">
          <div className="font-semibold tracking-wide">LEFT FOR THE APPLICANT — NOT {r.kind === 'signature' ? 'SIGNED' : 'TICKED'}</div>
          <div className="mt-1">Kanoe does not {r.kind === 'signature' ? 'sign' : 'tick this'}. Nothing we place here is {r.kind === 'signature' ? 'a signature' : 'your decision'}.</div>
          <div className="mt-1 text-slate-700">You must {r.the_person_must}.</div>
        </div>
      ) : (
        <>
          {r.value && <div className="mt-1 font-mono text-base">{r.value}</div>}
          {r.provenance && <div className="mt-0.5 text-xs text-slate-600">from: {r.provenance}</div>}
          {r.why && <div className="mt-0.5 text-xs text-slate-600">{r.why}</div>}
        </>
      )}
      {r.checks.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-xs">
          {r.checks.map((c, i) => <li key={i} className={VERDICT[c.level]}>reviewer: {c.level === 'ok' ? '✓' : c.level === 'check' ? '△' : '✗'} {c.why}</li>)}
        </ul>
      )}
    </li>
  )
}

export default async function RelocationFile({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const r = await productsGet<File>(`/relocation/${encodeURIComponent(id)}`)
  if (!r.ok) {
    return <main className="min-h-screen bg-white"><div className="mx-auto max-w-3xl px-4 py-12 text-slate-800"><h1 className="text-xl font-semibold">Your EX-01</h1><p className="mt-4">{r.message}</p></div></main>
  }
  const f = r.data
  const sections: string[] = []
  for (const row of f.rows) if (!sections.includes(row.section)) sections.push(row.section)
  const filled = f.counts.filled ?? 0
  const yours = f.counts.prepared_not_adopted ?? 0
  const noData = f.counts.blank_no_data ?? 0
  const noMap = f.counts.blank_no_mapping ?? 0
  const unplaced = f.counts.blank_unplaced ?? 0
  const na = f.counts.not_applicable ?? 0
  const sib = f.counts.answered_by_sibling ?? 0
  return (
    <main className="min-h-screen bg-white"><div className="mx-auto max-w-3xl px-4 py-8 text-slate-800">
      {f.fictional && (
        <p className="mb-4 rounded border border-violet-300 bg-violet-50 p-3 text-sm">Illustration: the applicant is fictional — every value marked “fictional demo applicant” is invented. The form and the checks are real.</p>
      )}
      <p className="text-sm font-medium uppercase tracking-wide text-slate-500">Prepared · not signed · not filed</p>
      <h1 className="mt-1 text-2xl font-semibold">{f.form.name} · {f.form.title}</h1>
      <p className="mt-1 text-slate-600">{f.form.widgets} fields read · {f.form.pages} pages · AcroForm</p>
      <ul className="mt-3 space-y-0.5 text-sm">
        <li><b>{filled}</b> filled from your answers, each naming its source{sib ? ` (and ${sib} box${sib === 1 ? '' : 'es'} on the same rows left unticked because your answer is the box beside them)` : ''}</li>
        <li><b>{yours}</b> left for you — we do not sign, consent or state your intent</li>
        <li><b>{noData}</b> blank because we hold nothing for them{noMap ? `; ${noMap} blank because nothing we hold answers them` : ''}{unplaced ? `; ${unplaced} not placed — a person classifies them first` : ''}</li>
        <li><b>{na}</b> blank because that part of the form isn’t your case</li>
      </ul>
      <p className="mt-2 text-sm">Reviewer: <span className={VERDICT.ok}>{f.checks.ok} fine</span> · <span className={VERDICT.check}>{f.checks.check} to look at</span> · <span className={VERDICT.problem}>{f.checks.problem} problem{f.checks.problem === 1 ? '' : 's'}</span></p>

      <section className="mt-5 rounded-lg border border-slate-300 p-4 text-sm">
        <p>Kanoe prepares this form. It does not file it. We fill what your answers and documents already say, we leave what only you can say, and we hand you the form. The application is yours to sign and yours to lodge{f.route === 'renewal' ? ' — renewals, electronically.' : ' — for a first application, on paper at a Spanish consulate.'}</p>
        <a href={`/api/products/relocation/${encodeURIComponent(id)}/EX-01-prepared.pdf`} className="mt-3 inline-block rounded bg-slate-900 px-4 py-2 text-white">Download the official PDF, prepared ↓</a>
        {f.signed_at && <p className="mt-2 text-slate-600">You told us you signed it on {at(f.signed_at)}. We didn’t sign or tick anything for you.</p>}
      </section>

      {/* CR 10 · said plainly, always: who does what, and where the checklist comes from */}
      <section className="mt-6 grid gap-3 text-sm sm:grid-cols-2">
        <div className="rounded-lg border border-slate-300 p-4">
          <h2 className="font-semibold">Sasha prepares</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>fills the official EX-01’s boxes from your answers, each naming where it came from;</li>
            <li>checks every field (postcode and province, the NIE’s control letter, text that won’t fit a box, your passport’s validity);</li>
            <li>finds your consulate’s own appointment route and document list — or says plainly when its page publishes none;</li>
            <li>drafts the appointment email where the consulate asks for one, and orders your document pack the way it lists them;</li>
            <li>reminds you of the dates that matter.</li>
          </ul>
        </div>
        <div className="rounded-lg border border-amber-400 p-4">
          <h2 className="font-semibold">You press</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>section 5 (first application or renewal; holder or family member);</li>
            <li>the Dehú consent — yours to decide;</li>
            <li>the signature, by hand, and the place and date;</li>
            <li>sending the appointment email (or booking), and lodging the application in person.</li>
          </ul>
          <p className="mt-2 text-xs text-slate-600">Sasha never signs, ticks a consent, books a government appointment or files anything for you.</p>
        </div>
      </section>
      {f.after?.consulate?.id ? (
        <p className="mt-3 text-xs text-slate-600">The document checklist comes from the {f.after.consulate.office}’s own page for this visa, read {f.after.consulate.source.read} ({f.after.consulate.source.dated}). It may change — the consulate’s current page decides.</p>
      ) : (
        <p className="mt-3 text-xs text-slate-600">The document checklist comes from the Spanish Consulate General in London’s own requirements sheet for this visa, dated 11 February 2022 (read 3 October 2026), or — for New York, Washington, Los Angeles, Miami and Boston — each consulate’s own page (read 3 October 2026). It may be out of date — the consulate’s current page decides.</p>
      )}

      {f.after && (
        <section className="mt-6 rounded-lg border border-sky-300 bg-sky-50 p-4 text-sm">
          <h2 className="text-base font-semibold">After you sign: you lodge it</h2>
          {f.after.consulate?.id ? (
            <>
              <p className="mt-2">Your consulate: <b>{f.after.consulate.office}</b>{f.after.state ? <> — {f.after.consulate.territory?.from ?? 'its page'}{f.after.consulate.territory?.dated ? ` (dated ${f.after.consulate.territory.dated})` : ''} names {f.after.county ? `${f.after.county}, ` : ''}{f.after.state}</> : null}.</p>
              {f.after.consulate.appointment_email ? (
                <p className="mt-1">How it takes appointments — its page, in its words: “{f.after.consulate.appointment_words.split('\n')[0]}”</p>
              ) : f.after.consulate.appointment_url ? (
                <p className="mt-1">Its appointment page: <a className="underline" href={f.after.consulate.appointment_url} target="_blank" rel="noopener noreferrer">{f.after.consulate.appointment_url}</a>. You book it; Kanoe doesn’t.</p>
              ) : (
                <p className="mt-1">Its page has the heading “Lugar de presentación” with nothing under it, so we can’t say how it takes appointments — and we don’t guess. Ask the consulate directly.</p>
              )}
              <p className="mt-1 text-xs text-slate-600">Source: <a className="underline" href={f.after.consulate.source.url} target="_blank" rel="noopener noreferrer">{f.after.consulate.source.name}</a> — {f.after.consulate.source.dated}, read {f.after.consulate.source.read}.</p>
              {f.after.consulate.general && <p className="mt-1 text-xs">Its page, on every foreign document: “{f.after.consulate.general}”</p>}
            </>
          ) : f.after.consulate ? (
            <>
              <p className="mt-2">Your consulate: <b>{f.after.consulate.office}</b>. Its own sheet: “{f.after.consulate.appointment_words}”:{' '}
                <a className="underline" href={f.after.consulate.appointment_url ?? '#'} target="_blank" rel="noopener noreferrer">{f.after.consulate.appointment_url}</a>.
                {' '}You book it and go in person; {f.after.consulate.one_per_person}. Kanoe doesn’t book or press anything.</p>
              <p className="mt-1 text-xs text-slate-600">Source: <a className="underline" href={f.after.consulate.source.url} target="_blank" rel="noopener noreferrer">{f.after.consulate.source.name}</a>, dated {f.after.consulate.source.dated}, read {f.after.consulate.source.read}. It may be out of date — the consulate’s current page decides.</p>
            </>
          ) : f.after.consulate_unreadable ? (
            <p className="mt-2">Your consulate is the <b>{f.after.consulate_unreadable.office}</b>, but {f.after.consulate_unreadable.why} — so there’s no checklist from it here, and we don’t make one up.</p>
          ) : (
            <p className="mt-2">We haven’t read the Spanish consulate’s own page for where you live, so we give no link we haven’t checked.</p>
          )}
          {f.after.checklist && (
            <ol className="mt-3 space-y-1">
              {f.after.checklist.map((c) => (
                <li key={c.key} className={c.status === 'problem' ? 'text-rose-700 font-semibold' : c.status === 'ok' || c.status === 'prepared' ? 'text-emerald-800' : c.status === 'not_needed' ? 'text-slate-500' : ''}>
                  {c.status === 'ok' || c.status === 'prepared' ? '✓' : c.status === 'problem' ? '✗' : c.status === 'not_needed' ? '—' : '☐'}{' '}
                  {c.n && c.label !== undefined ? <><b>{c.n}. {c.label ?? ''}</b> <span className="text-xs text-slate-500">(our label)</span> — <span lang="es">{c.words}</span></> : c.words}{c.why ? ` — ${c.why}` : ''}
                  {c.placeholder && <span className="ml-1 text-xs text-amber-800">(“{c.placeholder}” is the ministry template’s unfilled field, left on its page — not a requirement.)</span>}
                </li>
              ))}
            </ol>
          )}
          {f.after.email_draft && (
            <div className="mt-4 rounded border border-sky-400 bg-white p-3">
              <h3 className="font-semibold">The appointment email — drafted, for you to send</h3>
              <p className="mt-1 text-xs text-slate-600">Its page asks for an email with these details. Kanoe drafted it; you send it from your own address and attach the files yourself. Kanoe never sends it.</p>
              <p className="mt-2 text-xs">To: {f.after.email_draft.to} · Subject: {f.after.email_draft.subject}</p>
              <pre className="mt-1 whitespace-pre-wrap text-xs" lang="es">{f.after.email_draft.body}</pre>
              <a className="mt-2 inline-block rounded bg-sky-700 px-3 py-1.5 text-white" href={f.after.email_draft.mailto}>Open it in your email app — you press Send</a>
            </div>
          )}
          {f.after.pack && f.after.pack.length > 0 && (
            <div className="mt-4 rounded border border-emerald-400 bg-white p-3">
              <h3 className="font-semibold">Your document pack — in the consulate’s own order</h3>
              <p className="mt-1 text-xs text-slate-600">Name your files like this and they sort the way the consulate lists them. “Gathered” is on your word; Kanoe hasn’t seen the documents.</p>
              <ol className="mt-2 space-y-0.5 font-mono text-xs">
                {f.after.pack.map((x) => (
                  <li key={x.n} className={x.status === 'missing' ? 'text-slate-500' : 'text-emerald-800'}>
                    {x.status === 'missing' ? '☐' : '✓'} {x.name}{x.copies && x.status !== 'missing' ? ` — ${x.copies}` : ''}{x.status === 'missing' ? ' — still to gather' : ''}{x.status === 'prepared' ? ' — prepared by Kanoe; you sign it' : ''}
                  </li>
                ))}
              </ol>
            </div>
          )}
          <p className="mt-3">After you enter Spain, {f.after.consulate?.id ? 'the consulate’s page gives you' : 'the sheet gives you'} one month to request your TIE at an Oficina de Extranjería or police station. The official appointment page: <a className="underline" href="https://sede.administracionespublicas.gob.es/pagina/index/directorio/icpplus" target="_blank" rel="noopener noreferrer">Cita previa de extranjería</a>. You choose the office and press; we never book it.</p>
          {f.after.reminders && f.after.reminders.length > 0 && (
            <ul className="mt-3 space-y-0.5 text-xs text-slate-700">
              {f.after.reminders.map((r) => <li key={r.on}>⏰ {new Date(`${r.on}T12:00:00Z`).toUTCString().slice(5, 16)}: {r.text}{r.sent ? ' (sent)' : ''}</li>)}
            </ul>
          )}
        </section>
      )}

      {sections.map((sec) => (
        <section key={sec} className="mt-8">
          <h2 className="text-base font-semibold">{sec}</h2>
          <ol className="mt-2 space-y-2">{f.rows.filter((x) => x.section === sec).map((x) => <RowView key={x.name} r={x} />)}</ol>
        </section>
      ))}

      <p className="mt-10 text-xs text-slate-500">
        The official form, unaltered except for the boxes filled (sha256 {f.form.pdf_sha256.slice(0, 12)}…). Prepared {at(f.prepared_at)}; this page expires {at(f.expires_at)}.
        Kanoe Technologies SL · Calle Padre Damián 41, 28036 Madrid.
      </p>
    </div></main>
  )
}
