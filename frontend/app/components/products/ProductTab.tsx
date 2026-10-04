import type { CSSProperties } from 'react'
import { DemoLabel } from '../site/DemoLabel'
import { SiteShell } from '../site/SiteShell'
import s from '../site/site.module.css'
import { BRANDS, type ProductKey } from './brands'
import ProductChat from './ProductChat'
import b from './brand.module.css'

/**
 * CR 16 · one product tab: the brand's hero (copy from EU 150 — placeholders are outlined and say so), each feature with
 * its honest label (live · click-through · concept), and Sasha's own chat opened in this product's mode. Built on the
 * site's shell and label components (Sasha 123) so it reads as the same site. The Sasha tab mounts it on the existing
 * route when the founder lifts the site hold (Sasha 124); until then nothing links here.
 */
export default function ProductTab({ product }: { product: ProductKey }) {
  const brand = BRANDS[product]
  const k = brand.skin
  const vars = { '--brand-primary': k.primary, '--brand-accent': k.accent, '--brand-bg': k.bg, '--brand-ink': k.ink,
                 '--brand-soft': k.soft } as CSSProperties
  const ph = (t: string) => (t.startsWith('[COPY:') ? b.placeholder : undefined)
  return (
    <SiteShell>
      <div className={b.tab} style={vars}>
        <header className={b.hero}>
          <p className={b.kicker}>{brand.hero.kicker}</p>
          <h1 className={`${b.headline} ${ph(brand.hero.headline) ?? ''}`}>{brand.hero.headline}</h1>
          <p className={`${b.sub} ${ph(brand.hero.sub) ?? ''}`}>{brand.hero.sub}</p>
        </header>
        <ul className={b.features}>
          {brand.features.map((f) => (
            <li key={f.name} className={b.feature}>
              <DemoLabel kind={f.kind} sentence={f.name} />
              <span className={b.note}>— {f.note}</span>
            </li>
          ))}
        </ul>
        <ProductChat brand={brand} />
        <p className={s.legend}>LIVE — the real product · CLICK-THROUGH — a scripted walk · CONCEPT — designed, not built.
          TEST bookings issue no ticket and charge nothing.</p>
      </div>
    </SiteShell>
  )
}
