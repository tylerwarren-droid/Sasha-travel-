import Link from 'next/link'
import type { Metadata } from 'next'
import { SiteShell } from './components/site/SiteShell'

export const metadata: Metadata = {
  title: 'Not found — Kanoe',
  robots: { index: false, follow: false },
}

// Sasha 123 · a mistyped link lands in the new site, not the archive (the old version used the portal's shell).
export default function NotFound() {
  return (
    <SiteShell>
      <h1 style={{ fontSize: 32, marginBottom: 12 }}>This page doesn&apos;t exist</h1>
      <p style={{ marginBottom: 20 }}>The link may be out of date. Everything is reachable from the tabs above.</p>
      <Link href="/" style={{ textDecoration: 'underline' }}>Back to Kanoe</Link>
    </SiteShell>
  )
}
