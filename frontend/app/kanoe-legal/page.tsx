/**
 * S-71 · who operates Sasha — the legal identity Meta's reviewer (and anyone) looks for, on a domain we control:
 * kanoe.ai itself is hosted elsewhere (Apache, GoDaddy), so this is the business website given to Meta for
 * "Sasha by Kanoe". Facts only, as the founder gave them (Sasha 77).
 */
export const metadata = { title: 'Sasha by Kanoe — Kanoe Technologies SL' }

export default function KanoeLegal() {
  return (
    <main style={{ maxWidth: 640, margin: '10vh auto', padding: 24, fontFamily: 'system-ui, sans-serif', lineHeight: 1.6 }}>
      <h1>Sasha by Kanoe</h1>
      <p>Sasha by Kanoe is an AI concierge operated by Kanoe Technologies SL. She books restaurants and other venues for
        our guests by phone, email and messaging, and always says she is an AI.</p>
      <h2>Kanoe Technologies SL</h2>
      <p>NIF B23942923<br />Calle del Padre Damián 41, 28036 Madrid, Spain<br />
        <a href="mailto:tyler@kanoe.ai">tyler@kanoe.ai</a> · <a href="https://kanoe.ai">kanoe.ai</a></p>
      <p><a href="/sasha-privacy">How we handle your details (privacy notice)</a></p>
    </main>
  )
}
