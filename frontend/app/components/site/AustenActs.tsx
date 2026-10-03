import handelsregister from '../../(site)/content/austen/submit-www.handelsregister.de-2026-09-23.json'
import psi from '../../(site)/content/austen/submit-www.restaurante-psi.com-2026-09-23-d888a1b3.json'
import s from './site.module.css'

/** Sasha 123 · the AgAPI tab's LIVE records (§9.4): two acts exactly as recorded on 23 Sept 2026 — the fields shown are
 *  read from the records, and each links to the whole record — unchanged but for one email address redacted on the public
 *  copy (Sasha 124; AD's source record is untouched). */
type Rec = { intent: { ask: string; channel: string; target: { name: string }; authorised_by: { who: string; at: string } }
  approval: { approved_at: string }; outcome: { kind: string; target_said: { text: string } | null; next_action: string } }
const ACTS: { rec: Rec; file: string }[] = [
  { rec: handelsregister as unknown as Rec, file: 'submit-www.handelsregister.de-2026-09-23.json' },
  { rec: psi as unknown as Rec, file: 'submit-www.restaurante-psi.com-2026-09-23-d888a1b3.json' },
]

export function AustenActs() {
  return (
    <div className={s.acts}>
      {ACTS.map(({ rec, file }) => (
        <dl key={file} className={s.act}>
          <dt>Where</dt><dd>{rec.intent.target.name} · by its own {rec.intent.channel.replace('_', ' ')}</dd>
          <dt>The ask</dt><dd>{rec.intent.ask}</dd>
          <dt>The yes</dt><dd>{rec.intent.authorised_by.who}, {rec.approval.approved_at}</dd>
          <dt>The outcome, as recorded</dt>
          <dd><span className={rec.outcome.kind === 'confirmed' ? s.outcome_confirmed : s.outcome_other}>{rec.outcome.kind.toUpperCase()}</span>
            {rec.outcome.target_said ? <> — the page said: &ldquo;{rec.outcome.target_said.text}&rdquo;</> : null}</dd>
          <dt>Next</dt><dd>{rec.outcome.next_action}</dd>
          <dd><a href={`/data/austen/${file}`}>The whole record (JSON) →</a>{file.includes('restaurante-psi') ? ' One email address is redacted on this public copy; nothing else is changed.' : ' Unchanged.'}</dd>
        </dl>
      ))}
    </div>
  )
}
