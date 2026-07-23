import type { NextConfig } from 'next'
const nextConfig: NextConfig = {
  // StrictMode double-invokes effects in dev, which double-mounts SashaAvatar and
  // opens TWO parallel LiveAvatar sessions (desync + 2x credit burn). Prod builds
  // never double-invoke, so turning this off makes local dev match prod.
  reactStrictMode: false,

  // The portal used to be served statically as /sasha_investor.html. It is now a set of real
  // routes, so keep any already-shared link working instead of 404ing it.
  async redirects() {
    return [{ source: '/sasha_investor.html', destination: '/', permanent: false }]
  },
}
export default nextConfig
