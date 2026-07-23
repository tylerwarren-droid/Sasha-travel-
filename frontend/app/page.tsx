import type { Metadata } from 'next'
import PortalShell from './components/portal/PortalShell'
import Teaser from './components/portal/Teaser'

export const metadata: Metadata = {
  title: 'Kanoe.ai — Investor Portal',
  description: 'Kanoe.ai is an AI-first, crypto-native infrastructure layer for the B2B and D2C travel market.',
}

export default function Home() {
  return (
    <PortalShell>
      <Teaser />
    </PortalShell>
  )
}
