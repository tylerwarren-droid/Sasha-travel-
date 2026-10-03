import type { Metadata } from 'next'
import PortalShell from '../components/portal/PortalShell'
import Deck from '../components/portal/Deck'

export const metadata: Metadata = {
  robots: { index: false, follow: false },   // Sasha 123 · an archive page (kanoe-site-scope.md §9.1)
  title: 'Investor Deck — Kanoe.ai',
  description: 'Kanoe.ai investor presentation, 2026.',
}

export default function DeckPage() {
  return (
    <PortalShell>
      <Deck />
    </PortalShell>
  )
}
