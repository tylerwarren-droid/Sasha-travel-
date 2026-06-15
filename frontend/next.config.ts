import type { NextConfig } from 'next'
const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: '/',
        has: [{ type: 'host', value: 'investor.kanoe.ai' }],
        destination: '/sasha_investor.html',
        permanent: false,
      },
    ]
  },
  // StrictMode double-invokes effects in dev, which double-mounts SashaAvatar and
  // opens TWO parallel LiveAvatar sessions (desync + 2x credit burn). Prod builds
  // never double-invoke, so turning this off makes local dev match prod.
  reactStrictMode: false,
}
export default nextConfig
