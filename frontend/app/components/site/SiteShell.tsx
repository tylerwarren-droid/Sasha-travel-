import Link from 'next/link'
import type { ReactNode } from 'react'
import { DM_Sans, DM_Serif_Display } from 'next/font/google'
import { SiteNav } from './SiteNav'
import s from './site.module.css'

const body = DM_Sans({ subsets: ['latin'], weight: ['400', '500', '700'], display: 'swap', variable: '--site-body' })
const head = DM_Serif_Display({ subsets: ['latin'], weight: '400', display: 'swap', variable: '--site-head' })

/** Sasha 123 · the new project.kanoe.ai: header (logo → /), the six tabs, the page, and the legal footer (§9.3, §11). */
export function SiteShell({ children }: { children: ReactNode }) {
  return (
    <div className={`${s.page} ${body.variable} ${head.variable}`}>
      <header className={s.header}>
        <div className={s.headerInner}>
          <Link href="/" className={s.logo}>Kanoe</Link>
          <SiteNav />
        </div>
      </header>
      <main className={s.main}>{children}</main>
      <footer className={s.footer}>
        <div className={s.footerInner}>
          <span>© 2026 Kanoe Technologies SL · NIF B23942923 · Calle Padre Damián 41, 28036 Madrid</span>
          <a href="/sasha-privacy">Privacy</a>
          <a href="/archive">Original vision (archive) →</a>
        </div>
      </footer>
    </div>
  )
}
