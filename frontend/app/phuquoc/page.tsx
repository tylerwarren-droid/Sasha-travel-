'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

// The /phuquoc variant is not wired for the current demo (its voice gate + speak handoff were
// never connected, so it renders a dead avatar). Redirect to the live /vietnam demo so nobody
// lands on a broken page in front of investors. The original implementation remains in git
// history if this variant is revived later.
export default function PhuQuocRedirect() {
  const router = useRouter()
  useEffect(() => { router.replace('/vietnam') }, [router])
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#08081a', color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>
      Redirecting to Sasha…
    </div>
  )
}
