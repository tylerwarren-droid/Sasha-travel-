'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

// The portal's six sections are real routes now, so the nav is ordinary navigation and the
// active tab is derived from the URL instead of the old showPanel() class juggling.
export const PORTAL_TABS = [
  { href: '/', label: 'Teaser' },
  { href: '/deck', label: 'Investor Deck' },
  // NOTE: /onboarding is already taken by the B2B onboarding wizard app, so the portal's
  // walkthrough of that flow lives at /walkthrough.
  { href: '/walkthrough', label: 'Onboarding' },
  { href: '/tdm', label: 'TDM' },
  { href: '/data-strategy', label: 'Data Strategy' },
  { href: '/demo', label: 'Demo' },
] as const

export default function PortalNav({ right }: { right?: ReactNode }) {
  const pathname = usePathname()

  return (
    <nav>
      <Link href="/" className="nav-logo" aria-label="Kanoe.ai — home">
        {/* Intrinsic size is 1072x405; declaring the real dimensions keeps next/image's aspect
            ratio honest. Sizing is left entirely to `.nav-logo img` (height:38px; width:auto) —
            an inline height here modifies one axis and trips next/image's aspect-ratio warning. */}
        <Image src="/portal/logo.jpg" alt="Kanoe.ai" width={1072} height={405} priority sizes="150px" />
      </Link>

      <div className="nav-tabs">
        {PORTAL_TABS.map(tab => (
          <Link
            key={tab.href}
            href={tab.href}
            className={`nav-tab${pathname === tab.href ? ' active' : ''}`}
            aria-current={pathname === tab.href ? 'page' : undefined}
          >
            {tab.label}
          </Link>
        ))}
      </div>

      {/* Right-hand slot: only the Demo route fills it (with its demo switcher pills). */}
      {right ?? <div />}
    </nav>
  )
}
