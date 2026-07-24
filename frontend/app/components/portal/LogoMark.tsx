'use client'

import { useState } from 'react'

/**
 * Kanoe.ai logo that never shows a broken-image icon.
 *
 * The raster lives at /portal/logo.jpg. If that asset is missing from a deploy
 * (it is a binary in a new folder and has been dropped from a build before), the
 * <img> onError swaps in a styled "KANOE.ai" wordmark so the nav still reads as the
 * brand instead of a broken tile. Plain <img> (not next/image) is deliberate: it
 * avoids the /_next/image optimizer, which returns 400 when the source 404s.
 *
 * `height` is the rendered logo height in px; width follows the 1072x405 ratio.
 */
export default function LogoMark({
  height = 38,
  className,
}: {
  height?: number
  className?: string
}) {
  const [failed, setFailed] = useState(false)

  if (failed) {
    return (
      <span
        className={className}
        style={{
          fontFamily: 'system-ui, -apple-system, Segoe UI, sans-serif',
          fontWeight: 800,
          fontSize: height * 0.62,
          letterSpacing: '-0.01em',
          lineHeight: 1,
          whiteSpace: 'nowrap',
        }}
      >
        <span
          style={{
            background: 'linear-gradient(90deg,#5bc8ff,#3aa0ff)',
            WebkitBackgroundClip: 'text',
            backgroundClip: 'text',
            color: 'transparent',
          }}
        >
          KANOE
        </span>
        <span style={{ color: '#4ade80' }}>.ai</span>
      </span>
    )
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/portal/logo.jpg"
      alt="Kanoe.ai"
      className={className}
      onError={() => setFailed(true)}
      style={{ height, width: 'auto', objectFit: 'contain', display: 'block' }}
    />
  )
}
