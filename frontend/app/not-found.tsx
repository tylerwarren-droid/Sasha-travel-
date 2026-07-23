import Link from 'next/link'
import type { Metadata } from 'next'
import PortalShell from './components/portal/PortalShell'

export const metadata: Metadata = {
  title: 'Not found — Kanoe.ai',
}

// Without this, a mistyped portal URL fell through to Next's unstyled default 404 — jarring
// when the link came from an investor email. This keeps them inside the portal with the nav
// intact so they can reach the section they wanted.
export default function NotFound() {
  return (
    <PortalShell>
      <div className="panel active">
        <div style={{ maxWidth: 640, margin: '0 auto', padding: '120px 24px', textAlign: 'center' }}>
          <div style={{ fontSize: 12, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--teal)', marginBottom: 16 }}>
            404
          </div>
          <h1 style={{ fontFamily: 'var(--head)', fontSize: 40, lineHeight: 1.15, marginBottom: 14 }}>
            This page doesn&apos;t exist
          </h1>
          <p style={{ color: 'var(--muted)', fontSize: 15, marginBottom: 32 }}>
            The link may be out of date. Everything in the portal is reachable from the tabs above.
          </p>
          <Link
            href="/"
            style={{
              display: 'inline-block', background: 'var(--teal)', color: 'var(--navy)',
              fontSize: 14, fontWeight: 600, padding: '12px 28px', borderRadius: 8, textDecoration: 'none',
            }}
          >
            Back to the teaser
          </Link>
        </div>
      </div>
    </PortalShell>
  )
}
