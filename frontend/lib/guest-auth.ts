'use client'

/**
 * S-62 step 7 · the signed-in guest's access token for Sasha's backend calls (chat, classify, trips), so their chats are
 * theirs. The backend VERIFIES it (booking_signer/identity.py); with no session — guest sign-in closed, the public demo,
 * or the founder's own session — nothing is sent and the call is the demo's, as before.
 * The Supabase browser client refreshes an expiring token itself; call refreshGuestAuth() before a turn.
 */
import { createBrowserClient } from '@supabase/ssr'

let token: string | null = null
let client: ReturnType<typeof createBrowserClient> | null = null

export async function refreshGuestAuth(): Promise<void> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL, key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!url || !key) { token = null; return }
  try {
    client = client ?? createBrowserClient(url, key)
    const { data } = await client.auth.getSession()
    token = data.session?.access_token ?? null
  } catch {
    token = null   // no session can be read: the call goes as the demo's, never as someone else's
  }
}

export const guestAuth = (): Record<string, string> => (token ? { Authorization: `Bearer ${token}` } : {})
