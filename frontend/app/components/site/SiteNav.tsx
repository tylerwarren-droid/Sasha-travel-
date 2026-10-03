'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import s from './site.module.css'

/** Sasha 123 · the new site's six tabs (kanoe-site-scope.md §9.3). The archive is NOT here — a test pins that. */
export const SITE_TABS = [
  { href: '/',                  label: 'AgAPI' },
  { href: '/sasha',             label: 'Sasha' },
  { href: '/applied-diligence', label: 'Applied Diligence' },
  { href: '/campusme',          label: 'CampusMe' },
  { href: '/relocation',        label: 'Relocation' },
  { href: '/spain-services',    label: 'Spain public services' },
] as const

export function SiteNav() {
  const path = usePathname()
  return (
    <nav className={s.nav} aria-label="Kanoe">
      {SITE_TABS.map((t) => (
        <Link key={t.href} href={t.href} className={`${s.tab}${path === t.href ? ` ${s.active}` : ''}`} aria-current={path === t.href ? 'page' : undefined}>
          {t.label}
        </Link>
      ))}
    </nav>
  )
}
