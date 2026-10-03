import type { Metadata } from 'next'
import PortalShell from '../components/portal/PortalShell'
import DataStrategy from '../components/portal/DataStrategy'

export const metadata: Metadata = {
  robots: { index: false, follow: false },   // Sasha 123 · an archive page (kanoe-site-scope.md §9.1)
  title: 'Data Strategy — Kanoe.ai',
  description: 'How Kanoe turns its behavioural travel dataset into a second revenue stream.',
}

export default function DataStrategyPage() {
  return (
    <PortalShell>
      <DataStrategy />
    </PortalShell>
  )
}
