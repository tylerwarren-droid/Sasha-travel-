/**
 * Single source of truth for the backend (Conductor) base URL.
 *
 * Everything that talks to the FastAPI backend MUST import from here instead of
 * hardcoding `https://sasha-travel-production.up.railway.app`. That hardcoding was
 * scattered across pages/components, so moving the backend (e.g. Railway → an EU VM)
 * silently broke photo/conductor calls. With this module, one env var moves the whole
 * backend with zero code changes.
 *
 * Set `NEXT_PUBLIC_API_URL` in the deploy env (Vercel/Cloudflare). Falls back to the
 * Railway prod host so existing deployments keep working if the env var is missing.
 */

const FALLBACK_API_URL = 'https://sasha-travel-production.up.railway.app'

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL?.trim() || FALLBACK_API_URL
).replace(/\/+$/, '') // strip trailing slash so `${API_URL}/api/...` never doubles up

/** Optional shared secret the backend may require on public LLM endpoints (W6). */
export const CLIENT_KEY = process.env.NEXT_PUBLIC_CLIENT_KEY?.trim() || ''

/** Build a full backend URL from a path like `/api/agents/conductor`. */
export const apiUrl = (path: string): string =>
  `${API_URL}${path.startsWith('/') ? path : `/${path}`}`

/** Headers for backend calls — attaches the client key when configured. */
export const apiHeaders = (extra: Record<string, string> = {}): Record<string, string> => ({
  'Content-Type': 'application/json',
  ...(CLIENT_KEY ? { 'X-Client-Key': CLIENT_KEY } : {}),
  ...extra,
})
