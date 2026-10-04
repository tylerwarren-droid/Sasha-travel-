import type { Metadata } from 'next'
import Link from 'next/link'
import { DM_Sans, DM_Serif_Display } from 'next/font/google'
import s from '../components/site/site.module.css'
import Hub from './Hub'

const body = DM_Sans({ subsets: ['latin'], weight: ['400', '500', '700'], display: 'swap', variable: '--site-body' })
const head = DM_Serif_Display({ subsets: ['latin'], weight: '400', display: 'swap', variable: '--site-head' })

/**
 * Sasha 142 · THE HUB, project.kanoe.ai/agapi — the founder's structure (4 Oct 2026): the root is the Sasha Vietnam
 * site, and the new site lives here: AgAPI on top, then one tab per product. Copy: EU 152
 * (docs/business/agapi-hub-pitches.md), as typed data in ./content.ts.
 */
const TITLE = 'AgAPI — Kanoe'
const DESCRIPTION = 'One method, proven in five products: Sasha, Applied Diligence, CampusMe, RelocateMe and EspañaMe.'
export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  openGraph: { title: TITLE, description: DESCRIPTION, siteName: 'Kanoe', type: 'website', url: '/agapi' },
}

export default function Page() {
  return (
    <div className={`${s.page} ${body.variable} ${head.variable}`}>
      <header className={s.header}>
        <div className={s.headerInner}>
          <Link href="/agapi" className={s.logo}>Kanoe</Link>
          <Link href="/" className={s.tab}>Sasha (Vietnam) →</Link>
        </div>
      </header>
      <main className={s.main}>
        <Hub />
      </main>
      <footer className={s.footer}>
        <div className={s.footerInner}>
          <span>© 2026 Kanoe Technologies SL · NIF B23942923 · Calle Padre Damián 41, 28036 Madrid</span>
          <a href="/sasha-privacy">Privacy</a>
        </div>
      </footer>
    </div>
  )
}
