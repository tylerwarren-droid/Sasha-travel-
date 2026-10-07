import { NextResponse } from 'next/server'
import { CONTEXT_ID, OPENING_TEXT, PROMPT } from '@/lib/avatar-context.mjs'

// Sasha 200 · the LiveAvatar context, read and set with the key that lives only here (HEYGEN_API_KEY is a sensitive Vercel
// variable). Ops only: the x-sasha-booking-key header must equal SASHA_BOOKING_KEY. Never returns a key.
//   GET  → { opening_text, prompt, matches: { opening, prompt } }   — the check
//   POST { apply: true } → the context set to lib/avatar-context.mjs; returns what it was before (for rollback) and after
export const dynamic = 'force-dynamic'
const API = `https://api.liveavatar.com/v1/contexts/${CONTEXT_ID}`

function allowed(req: Request): boolean {
  const want = process.env.SASHA_BOOKING_KEY || ''
  return !!want && req.headers.get('x-sasha-booking-key') === want
}

async function read() {
  const r = await fetch(API, { headers: { 'X-API-KEY': process.env.HEYGEN_API_KEY as string }, cache: 'no-store' })
  const j = await r.json().catch(() => ({}))
  return { ok: r.ok, status: r.status, data: j?.data ?? null }
}

const view = (d: any) => d && ({
  name: d.name, opening_text: d.opening_text, prompt: d.prompt, updated_at: d.updated_at,
  matches: { opening: d.opening_text === OPENING_TEXT, prompt: d.prompt === PROMPT },
})

export async function GET(req: Request) {
  if (!allowed(req)) return NextResponse.json({ ok: false, rule: 'ops_only' }, { status: 403 })
  if (!process.env.HEYGEN_API_KEY) return NextResponse.json({ ok: false, rule: 'no_liveavatar_key' }, { status: 500 })
  const r = await read()
  if (!r.ok || !r.data) return NextResponse.json({ ok: false, rule: 'liveavatar_unreadable', status: r.status }, { status: 502 })
  return NextResponse.json({ ok: true, ...view(r.data) })
}

export async function POST(req: Request) {
  if (!allowed(req)) return NextResponse.json({ ok: false, rule: 'ops_only' }, { status: 403 })
  if (!process.env.HEYGEN_API_KEY) return NextResponse.json({ ok: false, rule: 'no_liveavatar_key' }, { status: 500 })
  const body = await req.json().catch(() => ({}))
  if (body?.apply !== true) return NextResponse.json({ ok: false, rule: 'say_apply_true' }, { status: 400 })
  const before = await read()
  if (!before.ok || !before.data) return NextResponse.json({ ok: false, rule: 'liveavatar_unreadable', status: before.status }, { status: 502 })
  const links = (before.data.links || []).map((l: any) => ({ url: l.url, faq: l.faq, ...(l.id ? { id: l.id } : {}) }))
  const r = await fetch(API, {
    method: 'PATCH',
    headers: { 'X-API-KEY': process.env.HEYGEN_API_KEY as string, 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: before.data.name, prompt: PROMPT, opening_text: OPENING_TEXT, links }),
  })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) return NextResponse.json({ ok: false, rule: 'liveavatar_refused', status: r.status, detail: j }, { status: 502 })
  const after = await read()
  return NextResponse.json({ ok: true, before: view(before.data), after: view(after.data) })
}
