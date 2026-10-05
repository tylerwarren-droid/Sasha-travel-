'use client'

import { useEffect, useState } from 'react'
import { CLAIM_GLYPH, CLAIM_WORD, FIG_WORD, HUB, PITCHES, type Line, type Pitch } from './content'
import h from './hub.module.css'

/**
 * Sasha 142 · the hub's body: AgAPI on top, then one tab per product (EU 152's pitches). A tab is shown only when its
 * copy is in (`ready`); the open tab follows the URL's #hash, so each pitch can be linked to.
 */
const SHOWN = PITCHES.filter((p) => p.ready)

function Mark({ line }: { line: Line }) {
  return (
    <li className={h.line}>
      <span className={h.mark} title={CLAIM_WORD[line.mark]} aria-label={CLAIM_WORD[line.mark]}>{CLAIM_GLYPH[line.mark]}</span>
      <span>{line.text}</span>
    </li>
  )
}

function PitchView({ p }: { p: Pitch }) {
  return (
    <article className={h.pitch} aria-labelledby={`t-${p.key}`}>
      <h2 id={`t-${p.key}`} className={h.pitchName}>
        {p.name}{p.badge && <span className={h.badge}>{p.badge}</span>}
        {p.tryHref && <a className={h.tryNow} href={p.tryHref}>Try it now →</a>}
      </h2>
      <p className={h.problem}><strong>The problem.</strong> {p.problem}</p>

      <h3 className={h.h3}>What it does</h3>
      <ul className={h.lines}>{p.does.map((l, i) => <Mark key={i} line={l} />)}</ul>

      <h3 className={h.h3}>How it uses AgAPI</h3>
      <dl className={h.agents}>
        {p.agents.map((a) => (
          <div key={a.agent} className={h.agentRow}>
            <dt>{a.agent}</dt>
            <dd><span className={h.mark} title={CLAIM_WORD[a.mark]}>{CLAIM_GLYPH[a.mark]}</span> {a.text}</dd>
          </div>
        ))}
      </dl>

      <h3 className={h.h3}>Market</h3>
      <div className={h.tableWrap}>
        <table className={h.table}>
          <thead><tr><th></th><th>Figure</th><th>Method</th><th>Mark</th></tr></thead>
          <tbody>
            {p.market.map((f, i) => (
              <tr key={i}>
                <th scope="row">{f.row}</th>
                <td>{f.figure}{f.note && <span className={h.note}> {f.note}</span>}</td>
                <td>
                  {f.method}
                  {f.sources.length > 0 && (
                    <span className={h.sources}>
                      {f.sources.map((s, j) => (
                        <a key={j} href={s.url} target="_blank" rel="noopener noreferrer"
                           title={s.read ? 'read at source' : 'seen in a search summary; the page itself was not opened'}>
                          {s.read ? '●' : '○'} source {j + 1}
                        </a>
                      ))}
                    </span>
                  )}
                </td>
                <td className={h.figMarks}>{f.marks.map((m) => <abbr key={m} title={FIG_WORD[m]}>[{m}]</abbr>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className={h.h3}>Business model</h3>
      <ul className={h.lines}>{p.model.map((l, i) => <Mark key={i} line={l} />)}</ul>

      <h3 className={h.h3}>Status</h3>
      <ul className={h.lines}>{p.status.map((l, i) => <Mark key={i} line={l} />)}</ul>

      <div className={h.demo}>
        {p.demo.href && <a className={h.demoLink} href={p.demo.href}>Open {p.demo.label} →</a>}
        <p className={h.whatsapp}><span className={h.waLabel}>On WhatsApp:</span> {p.demo.whatsapp}</p>
      </div>
    </article>
  )
}

export default function Hub() {
  const [open, setOpen] = useState(SHOWN[0]?.key)
  useEffect(() => {
    const pick = () => {
      const k = window.location.hash.slice(1)
      if (SHOWN.some((p) => p.key === k)) setOpen(k)
    }
    pick()
    window.addEventListener('hashchange', pick)
    return () => window.removeEventListener('hashchange', pick)
  }, [])
  const current = SHOWN.find((p) => p.key === open) ?? SHOWN[0]

  return (
    <>
      <section className={h.top} aria-labelledby="agapi">
        <p className={h.kicker} id="agapi">AgAPI</p>
        <h1 className={h.headline}>{HUB.headline}</h1>
        <div className={h.agentGrid}>
          {HUB.agents.map((a) => (
            <div key={a.name} className={h.agentCard}>
              <p className={h.agentName}>{a.name} <span className={h.agentRole}>{a.role}</span></p>
              <p className={h.agentText}>{a.text}</p>
            </div>
          ))}
        </div>
        <ul className={h.lines}>{HUB.status.map((l, i) => <Mark key={i} line={l} />)}</ul>
        <p className={h.whatsapp}>{HUB.whatsapp}</p>
      </section>

      <nav className={h.tabs} role="tablist" aria-label="Products">
        {SHOWN.map((p) => (
          <a key={p.key} href={`#${p.key}`} role="tab" aria-selected={p.key === current?.key}
             className={`${h.tab}${p.key === current?.key ? ` ${h.active}` : ''}`}>
            {p.name}
          </a>
        ))}
      </nav>

      {current && <PitchView p={current} />}

      <p className={h.legend}>
        Claims: ✅ built or live · 🧪 works, with TEST bookings or a fictional subject · ○ concept · ◐ founder-reported.
        Figures: [S] sourced · [V] vendor estimate · [E] our estimate, method shown · [F] founder assumption, left as a
        variable. Sources: ● read at source · ○ seen in a search summary. {HUB.marketKey} Research: 4 Oct 2026.
      </p>
    </>
  )
}
