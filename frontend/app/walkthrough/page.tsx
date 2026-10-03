import type { Metadata } from 'next'
import PortalShell from '../components/portal/PortalShell'
import Walkthrough from '../components/portal/Walkthrough'

export const metadata: Metadata = {
  robots: { index: false, follow: false },   // Sasha 123 · an archive page (kanoe-site-scope.md §9.1)
  title: 'B2B Onboarding — Kanoe.ai',
  description: 'Interactive walkthrough of the Kanoe B2B operator onboarding flow.',
}

export default function WalkthroughPage() {
  return (
    <PortalShell>
      <Walkthrough />
    </PortalShell>
  )
}
