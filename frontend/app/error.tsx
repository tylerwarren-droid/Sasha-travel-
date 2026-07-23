'use client'

import { useEffect } from 'react'

/**
 * App-wide client error boundary.
 *
 * Without one, an unhandled render error blanks the page — which in front of an investor, or
 * mid-demo on /vietnam, looks like the product died. This keeps something on screen and offers
 * a retry, which recovers from transient failures without a full reload.
 *
 * Deliberately self-contained (inline styles, no portal CSS import): it must still render when
 * the thing that failed is a stylesheet or a component the portal depends on.
 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error('[app error boundary]', error)
  }, [error])

  return (
    <div
      style={{
        minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24,
        background: '#040D1A', color: '#E8F4F0',
        fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
      }}
    >
      <div style={{ maxWidth: 520, textAlign: 'center' }}>
        <div style={{ fontSize: 12, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#00E5C0', marginBottom: 14 }}>
          Something went wrong
        </div>
        <h1 style={{ fontSize: 28, lineHeight: 1.2, marginBottom: 12, fontWeight: 600 }}>
          This page hit an unexpected error
        </h1>
        <p style={{ color: '#7BADA0', fontSize: 15, lineHeight: 1.6, marginBottom: 28 }}>
          Trying again usually clears it. If it keeps happening, the details are in the browser console.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={reset}
            style={{
              background: '#00E5C0', color: '#040D1A', border: 'none', borderRadius: 8,
              padding: '12px 28px', fontSize: 14, fontWeight: 600, cursor: 'pointer',
            }}
          >
            Try again
          </button>
          <a
            href="/"
            style={{
              background: 'transparent', color: '#00E5C0', border: '1px solid rgba(0,229,192,0.35)',
              borderRadius: 8, padding: '12px 28px', fontSize: 14, fontWeight: 500, textDecoration: 'none',
            }}
          >
            Go to the portal
          </a>
        </div>
        {error.digest && (
          <div style={{ marginTop: 22, fontSize: 11, color: 'rgba(123,173,160,0.5)' }}>
            Reference: {error.digest}
          </div>
        )}
      </div>
    </div>
  )
}
