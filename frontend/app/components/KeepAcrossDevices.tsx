'use client'

/**
 * Sasha 153 · "Keep this across devices: add your email" — OPTIONAL, and offered only AFTER a booking (never before one),
 * to an automatic private guest. The address goes to their own account (Supabase sends a confirmation link).
 */
import { useEffect, useState } from 'react'
import { BOOKED_EVENT } from '@/lib/guest-start'

export function KeepAcrossDevices() {
  const [show, setShow] = useState(false)
  const [email, setEmail] = useState('')
  const [said, setSaid] = useState<string | null>(null)
  useEffect(() => {
    const on = async () => {
      const w = await fetch('/api/auth/whoami', { cache: 'no-store' }).then((r) => r.json()).catch(() => null)
      if (w?.who === 'guest' && String(w.email ?? '').endsWith('@guests.kanoe.ai')) setShow(true)
    }
    window.addEventListener(BOOKED_EVENT, on)
    return () => window.removeEventListener(BOOKED_EVENT, on)
  }, [])
  if (!show) return null
  async function save() {
    const r = await fetch('/api/guest/email', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email }) })
    const j = await r.json().catch(() => ({})) as { say?: string; message?: string }
    setSaid(r.ok ? (j.say ?? 'Check your inbox.') : (j.message ?? `Not saved (HTTP ${r.status}).`))
  }
  return (
    <div style={{ margin: '8px 0', padding: '10px 12px', borderRadius: 10, background: 'rgba(255,255,255,0.06)', fontSize: 13 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Keep this across devices</div>
      {said ? <div>{said}</div> : (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="your email (optional)"
                 style={{ flex: '1 1 180px', padding: '6px 8px', borderRadius: 8, color: '#111' }} />
          <button type="button" onClick={save} style={{ padding: '6px 10px', borderRadius: 8, background: '#7c5cff', color: '#fff' }}>Add</button>
          <button type="button" onClick={() => setShow(false)} style={{ padding: '6px 10px', opacity: 0.7 }}>Not now</button>
        </div>
      )}
    </div>
  )
}
