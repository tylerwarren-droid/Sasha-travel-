/**
 * S-62 steps 3–4 · A GUEST's session: Supabase Auth (magic link), through @supabase/ssr's cookies. SERVER ONLY.
 *
 * ⛔ Closed unless GUEST_SIGN_IN_ENABLED=1 — set by the founder only after the leaked service-role key is rotated
 *    (S-62 step 0). Closed means: /sign-in says so, /auth/callback refuses, and no guest session is ever accepted.
 * The user is VERIFIED with Supabase (auth.getUser), never read from the cookie alone; the backend verifies the access
 * token's signature again (booking_signer/identity.py). Next 16 has no middleware of ours: the session is refreshed by
 * the route handlers that read it (they may set cookies), so the CTO's middleware.ts is untouched.
 */
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export function guestSignInOpen(): boolean {
  return (process.env.GUEST_SIGN_IN_ENABLED ?? '').trim() === '1'
}

export function supabaseConfigured(): boolean {
  return !!(process.env.NEXT_PUBLIC_SUPABASE_URL ?? '').trim() && !!(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? '').trim()
}

export async function guestClient() {
  const store = await cookies()
  return createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
    cookies: {
      getAll: () => store.getAll(),
      setAll: (all: { name: string; value: string; options?: Record<string, unknown> }[]) => {
        try {
          all.forEach(({ name, value, options }) => store.set(name, value, options))
        } catch { /* a Server Component cannot set cookies; the next route handler refreshes them */ }
      },
    },
  })
}

export type Guest = { id: string; email: string | null; accessToken: string }

/** The signed-in guest — verified with Supabase — or null. Never a guess, never the founder. */
export async function guest(): Promise<Guest | null> {
  if (!guestSignInOpen() || !supabaseConfigured()) return null
  const supabase = await guestClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) return null
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.access_token) return null
  return { id: user.id, email: user.email ?? null, accessToken: session.access_token }
}

/** A same-site path to return to after sign-in; anything else becomes the chat. */
export function safeNext(next: string | null | undefined): string {
  return typeof next === 'string' && /^\/(?!\/)[\w\-./?=&%]*$/.test(next) ? next : '/demo'
}
