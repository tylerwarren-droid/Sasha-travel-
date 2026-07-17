import type { NextConfig } from 'next'
const nextConfig: NextConfig = {
  // StrictMode double-invokes effects in dev, which double-mounts SashaAvatar and
  // opens TWO parallel LiveAvatar sessions (desync + 2x credit burn). Prod builds
  // never double-invoke, so turning this off makes local dev match prod.
  reactStrictMode: false,
}
export default nextConfig
