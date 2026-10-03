import type { Tab } from '../../(site)/content/types'
import { AustenActs } from './AustenActs'
import { DemoLabel } from './DemoLabel'
import { Mark } from './Mark'
import { SiteShell } from './SiteShell'
import s from './site.module.css'

/** Sasha 123 · ONE layout for every tab (§9.3, §11): the headline, three marked lines, the status line (always shown,
 *  styled as status), and the demo with its label. The content is data; nothing here can show a claim without a mark. */
export function TabPage({ tab }: { tab: Tab }) {
  return (
    <SiteShell>
      <h1 className={s.headline}>{tab.headline}</h1>
      <ul className={s.lines}>
        {tab.lines.map((l, i) => (
          <li key={i} className={s.line}><Mark status={l.status} evidence={l.evidence} /><span>{l.text}</span></li>
        ))}
      </ul>
      <p className={s.status}><span className={s.statusLabel}>Status:</span>{tab.statusLine}</p>
      <section className={s.demo} aria-label="Demo">
        <DemoLabel kind={tab.demo.kind} sentence={tab.demo.sentence} />
        {tab.demo.austen && <AustenActs />}
        {tab.demo.note && <p className={s.legend}>{tab.demo.note}</p>}
        {tab.demo.links && tab.demo.links.length > 0 && (
          <ul className={s.demoLinks}>
            {tab.demo.links.map((a) => (
              <li key={a.href}>{a.external ? <a href={a.href} target="_blank" rel="noopener noreferrer">{a.label}</a> : <a href={a.href}>{a.label}</a>}</li>
            ))}
          </ul>
        )}
      </section>
      <p className={s.legend}>✅ proven — in code, a live record or a saved source · ◐ founder-reported · ○ concept: designed, not built. Hover a mark for its evidence.</p>
    </SiteShell>
  )
}
