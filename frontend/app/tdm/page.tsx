import type { Metadata } from 'next'
import PortalShell from '../components/portal/PortalShell'
import Tdm from '../components/portal/Tdm'

export const metadata: Metadata = {
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
