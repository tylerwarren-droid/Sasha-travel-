import type { CSSProperties } from 'react'
import { DemoLabel } from '../site/DemoLabel'
import { Mark } from '../site/Mark'
import { SiteShell } from '../site/SiteShell'
import s from '../site/site.module.css'
import { BRANDS, type ProductKey } from './brands'
import ProductChat from './ProductChat'
import b from './brand.module.css'

/**
 * CR 16 · one product tab: EU 150's copy (docs/business/product-tabs-copy.md) — the badge on top where the tab is a
 * concept, the hero, three marked lines, the status line always shown in the tab's colours — and Sasha's own chat
 * opened in this product's mode. Built on the site's shell and marks (Sasha 123). The Sasha tab mounts it on the
 * existing route when the founder lifts the site hold (Sasha 124); until then only the unlinked /preview shows it.
 */
export default function ProductTab({ product }: { product: ProductKey }) {
  const brand = BRANDS[product]
  const k = brand.skin
  const vars = { '--brand-primary': k.primary, '--brand-accent': k.accent, '--brand-bg': k.bg, '--brand-ink': k.ink,
                 '--brand-soft': k.soft } as CSSProperties
  return (
    <SiteShell>
      <div className={b.tab} style={vars}>
        {brand.badge && <div className={b.badge}><DemoLabel kind="concept" sentence={brand.badge} /></div>}
        <header className={b.hero}>
          <p className={b.kicker}>{brand.name}</p>
          <h1 className={b.headline}>{brand.hero}</h1>
        </header>
        <ul className={s.lines}>
          {brand.lines.map((l, i) => (
            <li key={i} className={s.line}>
              <Mark status={l.mark === 'built' ? 'proven' : 'concept'} evidence={l.cite} /><span>{l.text}</span>
            </li>
          ))}
        </ul>
        <p className={b.status}><span className={b.statusLabel}>Status:</span> {brand.statusLine}</p>
        <ProductChat brand={brand} />
        <p className={s.legend}>✅ built and rehearsed · ○ concept: designed, not built. Hover a mark for its evidence. TEST
          bookings issue no ticket and charge nothing.</p>
      </div>
    </SiteShell>
  )
}
