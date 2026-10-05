'use client'

/**
 * S-62 step 7 · the signed-in guest's access token for Sasha's backend calls (chat, classify, trips), so their chats are
 * theirs. The backend VERIFIES it (booking_signer/identity.py); with no session — guest sign-in closed, the public demo,
 * nothing is sent and the call is the PUBLIC demo's: its own empty account, never the founder's (Sasha 142).
 * The founder's own session goes through the same-origin pass-through (/api/sasha/…), which adds his session.
 * The Supabase browser client refreshes an expiring token itself; call refreshGuestAuth() before a turn.
 */
import { createBrowserClient } from '@supabase/ssr'
import { apiUrl } from './api'
import { ensureGuest } from './guest-start'

let token: string | null = null
let client: ReturnType<typeof createBrowserClient> | null = null

let founder: boolean | null = null

/** Sasha 142 · is this browser the founder's signed-in session? Asked once per page (the cookie is httpOnly). */
async function refreshFounder(): Promise<void> {
  if (founder !== null) return
  try {
    const r = await fetch('/api/founder-session', { cache: 'no-store' })
    founder = r.ok && (await r.json())?.signed_in === true
  } catch {
    founder = false   // can't tell: the call goes as the public demo's — never as the founder's
  }
}

export async function refreshGuestAuth(): Promise<void> {
  await refreshFounder()
  await readGuest()
  // Sasha 153 · no sign-in wall: a browser with no account gets its own automatic private guest account, then reads it
  if (!founder && !token && (await ensureGuest())) await readGuest()
}

async function readGuest(): Promise<void> {
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

/** Sasha 142 · where an account-scoped call goes: the founder's session through /api/sasha/… (his account); everyone
 *  else straight to the backend, as before (a guest with their token, a visitor as the public demo). */
export const accountUrl = (path: string): string =>
  founder ? `/api/sasha/${path.replace(/^\//, '').replace(/^api\//, '')}` : apiUrl(path)
