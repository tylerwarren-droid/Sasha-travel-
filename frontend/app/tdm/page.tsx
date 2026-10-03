import type { Metadata } from 'next'
import PortalShell from '../components/portal/PortalShell'
import Tdm from '../components/portal/Tdm'

export const metadata: Metadata = {
  robots: { index: false, follow: false },   // Sasha 123 · an archive page (kanoe-site-scope.md §9.1)
  title: 'TDM — Kanoe.ai',
  description: 'Kanoe.ai technical design and roadmap deck.',
}

export default function TdmPage() {
  return (
    <PortalShell>
      <Tdm />
    </PortalShell>
  )
}
