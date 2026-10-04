import { productsGet } from '@/lib/products'
import { DemoLabel } from '../site/DemoLabel'
import b from './brand.module.css'

/**
 * CR 17 · EspañaMe's six areas — the SAME cards Sasha's chat shows (backend/products/health/espana.py, served at
 * /api/booking/products/espana/areas): what you need · the official route · what Sasha prepares · you press. Only Salud is
 * live; the rest are concepts. An area whose official page hasn't been read says so and shows no route.
 */
type Area = { key: string; name: string; live: boolean; need: string[]; route: string | null; route_url: string | null
              prepare: string; press: string; source: string | null; read: boolean; unread?: string[] }

export default async function EspanaAreas() {
  const r = await productsGet<{ areas: Area[] }>('/espana/areas')
  if (!r.ok) return <p className={b.status}>The areas couldn’t be loaded just now ({r.message}).</p>
  return (
    <section className={b.areas} aria-label="Spain's public processes">
      {r.data.areas.map((a) => (
        <article key={a.key} className={b.area}>
          <DemoLabel kind={a.live ? 'live' : 'concept'} sentence={a.name} />
          {!a.read ? (
            <p className={b.areaNote}>Its official page hasn’t been read yet{a.unread?.length ? ` (${a.unread.join('; ')})` : ''}, so no list and no route here — nothing from memory.</p>
          ) : (
            <dl className={b.areaParts}>
              {a.need.length > 0 && <><dt>What you need</dt><dd>{a.need.join(' · ')}</dd></>}
              {a.route && <><dt>The official route</dt><dd>{a.route}{a.route_url && <> — <a href={a.route_url} target="_blank" rel="noopener noreferrer">its own page ↗</a></>}</dd></>}
              <dt>{a.live ? 'What Sasha prepares' : 'What Sasha would prepare'}</dt><dd>{a.prepare}</dd>
              <dt>You press</dt><dd>{a.press}</dd>
              {a.unread && a.unread.length > 0 && <><dt>Not read yet</dt><dd>{a.unread.join('; ')}</dd></>}
            </dl>
          )}
          {a.source && <p className={b.areaNote}>Source: {a.source}</p>}
        </article>
      ))}
    </section>
  )
}
