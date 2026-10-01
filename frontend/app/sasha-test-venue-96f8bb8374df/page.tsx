/**
 * Sasha 75 · a TEST "venue" for proving the email rung end to end without bothering a real one. Its own website
 * publishes the founder's address, because the email rung writes only to an address read on the venue's own site —
 * never one typed in. Not indexed, at an unguessable path; to be removed once the email-rung proof is done.
 */
export const metadata = { title: 'Sasha test venue (not a restaurant)', robots: { index: false, follow: false } }

const ld = {
  '@context': 'https://schema.org',
  '@type': 'Restaurant',
  name: 'Sasha test venue',
  email: 'tyler@kanoe.ai',
  address: { '@type': 'PostalAddress', addressLocality: 'Madrid', addressCountry: 'ES' },
}

export default function TestVenue() {
  return (
    <main style={{ maxWidth: 560, margin: '10vh auto', padding: 24, fontFamily: 'system-ui, sans-serif', lineHeight: 1.5 }}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ld) }} />
      <h1>Sasha test venue</h1>
      <p>This is <strong>not a restaurant</strong>. It is a test page Kanoe Technologies SL uses to check that Sasha&rsquo;s
        booking emails are sent and that replies reach the right reservation. Reservations: <a href="mailto:tyler@kanoe.ai">tyler@kanoe.ai</a>.</p>
    </main>
  )
}
