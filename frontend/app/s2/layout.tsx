import type { Metadata, Viewport } from 'next'

// Sasha 221 · S2's own front door: the public name is just "Sasha"; installable as its own app (scope /s2)
export const metadata: Metadata = {
  title: 'Sasha',
  description: 'Your personal concierge',
  manifest: '/s2/manifest.webmanifest',
  appleWebApp: { capable: true, title: 'Sasha', statusBarStyle: 'black-translucent' },
  icons: { apple: '/pwa-icon/180' },
}
export const viewport: Viewport = { width: 'device-width', initialScale: 1, viewportFit: 'cover', themeColor: '#0b0b10' }

export default function S2Layout({ children }: { children: React.ReactNode }) {
  return children
}
