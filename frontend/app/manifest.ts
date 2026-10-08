import type { MetadataRoute } from 'next'

// Sasha 214 · Add to Home Screen: Sasha full-screen, opening straight into the conversation
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Sasha — AI travel concierge',
    short_name: 'Sasha',
    description: 'Talk to Sasha: she plans, finds places and books them — only after your yes.',
    start_url: '/next',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: '#0b0b12',
    theme_color: '#0b0b12',
    icons: [
      { src: '/pwa-icon/192', sizes: '192x192', type: 'image/png' },
      { src: '/pwa-icon/512', sizes: '512x512', type: 'image/png' },
      { src: '/pwa-icon/512', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  }
}
