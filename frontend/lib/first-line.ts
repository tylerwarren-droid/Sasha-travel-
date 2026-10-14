/**
 * Sasha 265 · item 5 (row 935, Tyler: "an IMMEDIATE first line, under 1 s") — voice.first_line, read from the backend ONCE
 * (GET /api/agent/first-line: its words and its rule for a request for work). The page says it the instant such a request is sent;
 * the stream's own first line (`first: true`) is the same words and is then not said twice. One truth: the words and the rule live in
 * backend/app/agent/voice.py — nothing here decides them.
 */
import { apiUrl } from '@/lib/api'

let rule: { line: string; re: RegExp } | null = null
let loading: Promise<void> | null = null

export function loadFirstLine(): Promise<void> {
  if (rule || loading) return loading || Promise.resolve()
  loading = fetch(apiUrl('/api/agent/first-line'), { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : null))
    .then((j: { line?: string; work?: string; flags?: string } | null) => {
      if (j?.line && j?.work) rule = { line: j.line, re: new RegExp(j.work, j.flags || 'i') }
    })
    .catch(() => { /* not read: the stream's own first line still comes (~1 s) */ })
    .finally(() => { loading = null })
  return loading
}

/** The first line for this message, when it is a request for work (and the rule has been read); else null. */
export function firstLineFor(text: string): string | null {
  return rule && rule.re.test(text || '') ? rule.line : null
}
