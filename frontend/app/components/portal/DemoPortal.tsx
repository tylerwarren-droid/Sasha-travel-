'use client'

import { useState } from 'react'
import PortalShell from './PortalShell'

type DemoKey = 'lt' | 'vn' | 'pq'

// The Vietnam concierge is part of THIS app, so its demo points at our own route rather than
// at a hardcoded Vercel URL. That hardcoded origin meant the Demo tab always framed the
// deployed build: running the portal locally still showed production inside the iframe, so
// local changes to /vietnam never appeared here and looked like they had failed to apply.
// A same-origin path follows whatever it is served from — localhost in dev, the deployment
// in production. Luxurious Traveler stays absolute: it is a separate product on its own host.
const DEMOS: { key: DemoKey; label: string; src: string; title: string }[] = [
  { key: 'lt', label: 'Luxurious Traveler', src: 'https://demo.kanoe.ai/chat', title: 'Luxurious Traveler demo' },
  { key: 'vn', label: 'Vietnam', src: '/vietnam', title: 'Vietnam concierge demo' },
  { key: 'pq', label: 'Phu Quoc', src: '/phuquoc', title: 'Phu Quoc demo' },
]

function Pills({ active, onSelect }: { active: DemoKey; onSelect: (k: DemoKey) => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 3, background: 'var(--navy3)', border: '1px solid var(--border)', borderRadius: 50, padding: 3 }}>
        {DEMOS.map(d => {
          const on = d.key === active
          return (
            <button
              key={d.key}
              onClick={() => onSelect(d.key)}
              aria-pressed={on}
              style={{
                padding: '5px 15px', borderRadius: 50, border: 'none', cursor: 'pointer',
                fontFamily: 'var(--body)', fontSize: 12, transition: 'all 0.2s',
                background: on ? 'var(--teal)' : 'transparent',
                color: on ? 'var(--navy)' : 'var(--muted)',
                fontWeight: on ? 600 : 500,
                animation: on ? 'pillGlow 2s ease-in-out infinite' : 'none',
              }}
            >
              {d.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function DemoPortal() {
  const [active, setActive] = useState<DemoKey>('vn')  // the demo IS Vietnam — open on it
  const current = DEMOS.find(d => d.key === active)!

  return (
    <PortalShell navRight={<Pills active={active} onSelect={setActive} />}>
      {/* Only the selected demo is mounted. That is deliberate and load-bearing: the original
          switchDemo() tore the iframe out of the DOM rather than hiding it, because a hidden
          demo keeps its WebRTC session and audio alive. Keying on `active` makes React unmount
          the old iframe and build the new one, which reproduces that exactly. */}
      <div
        id="panel-demo"
        style={{ padding: 0, paddingTop: 66, height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
      >
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          <iframe
            key={active}
            src={current.src}
            title={current.title}
            allow="autoplay;microphone;camera;fullscreen"
            style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
          />
        </div>
      </div>
    </PortalShell>
  )
}
