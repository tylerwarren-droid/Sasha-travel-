'use client'

import { useEffect, useState, useSyncExternalStore } from 'react'
import QRCode from 'qrcode'

/**
 * Sasha 228 · /next's "ADD FROM YOUR PHONE": the booking needs a passport and the Keep has none. A QR code + a short link that
 * opens /s2 straight to Add my passport on the phone — the same account, a one-time code, 10 minutes. The phone is never signed
 * in; the code permits that one passport photo and nothing else. When it's confirmed the page hears `keep_added` and this card
 * says what was added — the mask only ("Passport ES ••••456").
 */
export default function KeepHandoff({ code, what, expiresAt, added }: { code: string; what: string; expiresAt?: string; added?: string | null }) {
  const origin = useSyncExternalStore(() => () => {}, () => window.location.origin, () => '')
  const [qr, setQr] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const link = origin ? `${origin}/h/${code}` : ''
  useEffect(() => {
    if (!link) return
    QRCode.toDataURL(link, { margin: 1, width: 360, errorCorrectionLevel: 'M', color: { dark: '#111111', light: '#ffffff' } })
      .then(setQr).catch(() => setQr(null))
  }, [link])
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 15000); return () => clearInterval(t) }, [])
  const expired = !added && !!expiresAt && Date.parse(expiresAt) < now
  const until = expiresAt ? new Date(expiresAt).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : null
  const label = what === 'loyalty' ? 'loyalty card' : 'passport'
  return (
    <div className="lw-card" data-testid="keep-handoff">
      <div className="lw-cardHd"><span className="lw-ci gold">{added ? '✅' : '📱'}</span><div className="lw-meta">
        <div className="lw-k">{added ? 'Added to your Keep' : 'Add from your phone'}</div>
        <div className="lw-h">{added ? added : expired ? 'This code has expired — ask Sasha for a new one' : `Scan to add your ${label}`}</div></div></div>
      {!added && !expired && (
        <div className="lw-cardBody" style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          {qr ? <img src={qr} alt={`QR code: add your ${label} from your phone`} width={150} height={150} style={{ borderRadius: 10, background: '#fff' }} />
            : <div style={{ width: 150, height: 150, borderRadius: 10, background: 'rgba(255,255,255,.08)' }} />}
          <div style={{ flex: '1 1 180px', minWidth: 0 }}>
            <div className="o2" style={{ fontSize: 13.5, lineHeight: 1.45 }}>Point your phone&rsquo;s camera at the code, then take a photo of your {label === 'passport' ? "passport's photo page" : 'card'}. It&rsquo;s read once and not kept — only a masked number is saved, encrypted.</div>
            {link && <a href={link} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 8, color: '#E8B923', fontSize: 13.5, fontWeight: 600, wordBreak: 'break-all' }}>{link.replace(/^https?:\/\//, '')}</a>}
            <div className="o2" style={{ fontSize: 12, opacity: 0.7, marginTop: 6 }}>One use{until ? ` · until ${until}` : ''} · this account only</div>
          </div>
        </div>)}
    </div>
  )
}
