// Sasha 221 · /s2 installs to the home screen as "Sasha" (its own scope; /next keeps app/manifest.ts)
export const dynamic = 'force-static'

export function GET(): Response {
  return Response.json({
    name: 'Sasha', short_name: 'Sasha', description: 'Your personal concierge',
    start_url: '/s2', scope: '/s2', display: 'standalone', orientation: 'portrait',
    background_color: '#0b0b10', theme_color: '#0b0b10',
    icons: [{ src: '/pwa-icon/192', sizes: '192x192', type: 'image/png' }, { src: '/pwa-icon/512', sizes: '512x512', type: 'image/png' },
            { src: '/pwa-icon/512', sizes: '512x512', type: 'image/png', purpose: 'maskable' }],
  }, { headers: { 'content-type': 'application/manifest+json' } })
}
