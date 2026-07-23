import type { Metadata } from 'next'
import PortalShell from '../components/portal/PortalShell'
import DataStrategy from '../components/portal/DataStrategy'

export const metadata: Metadata = {
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
