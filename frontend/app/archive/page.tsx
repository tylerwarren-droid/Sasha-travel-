import type { Metadata } from 'next'
import PortalShell from '../components/portal/PortalShell'
import Teaser from '../components/portal/Teaser'

// Sasha 123 · "Original vision (archive)": the site's previous home page, moved here VERBATIM (kanoe-site-scope.md §9.1).
// Unlisted: not in the new menu, reached by one footer link, not indexed.
export const metadata: Metadata = {
  title: 'Kanoe.ai — Investor Portal',
  description: 'Kanoe.ai is an AI-first, crypto-native infrastructure layer for the B2B and D2C travel market.',
  robots: { index: false, follow: false },
}

export default function Home() {
  return (
    <PortalShell>
      <Teaser />
    </PortalShell>
  )
}
