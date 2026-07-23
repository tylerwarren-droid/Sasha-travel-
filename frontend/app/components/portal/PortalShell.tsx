'use client'

import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { DM_Sans, DM_Serif_Display } from 'next/font/google'
import PortalNav from './PortalNav'
import './portal.css'

// The portal CSS asks for 'DM Sans' / 'DM Serif Display' by family name. Serving them through
// next/font instead of the original <link> to Google keeps them self-hosted and drops a
// render-blocking third-party request.
const dmSans = DM_Sans({ subsets: ['latin'], weight: ['300', '400', '500'], display: 'swap' })
const dmSerif = DM_Serif_Display({ subsets: ['latin'], weight: '400', style: ['normal', 'italic'], display: 'swap' })

/**
 * Chrome shared by every investor-portal route: the stylesheet, the nav, and the one body
 * reset the portal needs.
 *
 * The root layout puts Tailwind's `flex flex-col` on <body> for the concierge app. The portal
 * was authored as a standalone document expecting normal block flow, and that flex context
 * collapses its fixed nav and 100vh panels — so portal routes opt out of it while mounted and
 * restore it on the way out, leaving /vietnam untouched.
 */
export default function PortalShell({ children, navRight }: { children: ReactNode; navRight?: ReactNode }) {
  useEffect(() => {
    const { body } = document
    const previous = body.className
    body.classList.add('portal-body')
    body.classList.remove('flex', 'flex-col', 'min-h-full')
    return () => { body.className = previous }
  }, [])

  return (
    <>
      {/* Point the stylesheet's font variables at the next/font families. */}
      <style>{`:root{--body:${dmSans.style.fontFamily};--head:${dmSerif.style.fontFamily}}`}</style>
      <PortalNav right={navRight} />
      {children}
    </>
  )
}
