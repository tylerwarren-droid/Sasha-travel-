import Link from 'next/link'
import type { ReactNode } from 'react'
import { siteBody as body, siteHead as head } from '../../fonts/fonts'   // Sasha 358 · the fonts are in the repo
import { SiteNav } from './SiteNav'
import s from './site.module.css'


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
          <a href="/">Kanoe.ai portal →</a>
        </div>
      </footer>
    </div>
  )
}
