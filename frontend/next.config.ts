import type { NextConfig } from 'next'
const nextConfig: NextConfig = {
  // StrictMode double-invokes effects in dev, which double-mounts SashaAvatar and
  // opens TWO parallel LiveAvatar sessions (desync + 2x credit burn). Prod builds
  // never double-invoke, so turning this off makes local dev match prod.
  reactStrictMode: false,

  // The portal used to be served statically as /sasha_investor.html. It is now a set of real
  // routes, so keep any already-shared link working instead of 404ing it.
  async redirects() {
    return [
      { source: '/sasha_investor.html', destination: '/', permanent: false },
      // Sasha 143 · the hub (/agapi) supersedes the Sasha 123 six-tab pages: each goes to its own tab there
      { source: '/sasha', destination: '/agapi#sasha', permanent: false },
      { source: '/applied-diligence', destination: '/agapi#applied-diligence', permanent: false },
      { source: '/campusme', destination: '/agapi#campusme', permanent: false },
      { source: '/relocation', destination: '/agapi#relocateme', permanent: false },
      { source: '/spain-services', destination: '/agapi#espaname', permanent: false },
    ]
  },
}
export default nextConfig
