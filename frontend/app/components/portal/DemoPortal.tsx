'use client'

import { useState } from 'react'
import PortalShell from './PortalShell'
import { SASHA } from '@/lib/routes'   // Sasha 368 · the ONE route map

type DemoKey = 'sasha'

// Sasha 368 · the Demo tab opens TODAY's Sasha (lib/routes.ts SASHA = /s2, the 364–367 work) — never an older Sasha page (before 3 Oct it
// framed Luxurious Traveler, the Vietnam page and Phu Quoc). A same-origin path: it follows whatever it is served from.
const DEMOS: { key: DemoKey; label: string; src: string; title: string }[] = [
  { key: 'sasha', label: 'Sasha', src: SASHA, title: 'Sasha — AI concierge' },
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
  const [active, setActive] = useState<DemoKey>('sasha')  // Sasha 368 · the demo IS today's Sasha
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
