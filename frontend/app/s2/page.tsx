import S2App, { S2Handoff } from './S2App'

// Sasha 221 · project.kanoe.ai/s2 — Sasha, the personal concierge (S2). S1 stays at /next, untouched.
// Sasha 228 · /s2?handoff=<code> — the phone end of /next's "Add from your phone" (straight to Add my passport).
export default async function S2Page({ searchParams }: { searchParams: Promise<{ handoff?: string | string[] }> }) {
  const h = (await searchParams).handoff
  const code = typeof h === 'string' && /^[a-z0-9]{6,32}$/.test(h) ? h : null
  return code ? <S2Handoff code={code} /> : <S2App />
}
