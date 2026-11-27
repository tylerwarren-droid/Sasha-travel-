// Sasha 423 · 424 · NO TERM WITHOUT A FACT — the frontend half of backend/tests/test_s423_no_term_without_a_fact.py (the gate runs
// with backend/ only, so the page's half is pinned here, in npm test — run by CI on every PR and on main).
// A booking's terms (refundable, a cancellation rule, a deadline, a fee) are AgAPI's facts (facts.answer) or not shown: no type holds a
// term field, no component composes one, no screen says "Refundable" / "Free cancellation" from a field of Sasha's.
//   node --test scripts/no-term-424.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const SKIP = new Set(['node_modules', '.next', '.vercel', 'scripts'])

function files(dir, out = []) {
  for (const n of readdirSync(dir)) {
    if (SKIP.has(n)) continue
    const p = join(dir, n)
    if (statSync(p).isDirectory()) files(p, out)
    else if (/\.(ts|tsx)$/.test(n)) out.push(p)
  }
  return out
}
const SRC = files(ROOT).map((p) => ({ p: relative(ROOT, p), t: readFileSync(p, 'utf8') }))

// the backend ratchet's name rule, the same words
const TERM_FIELD = /^(?:is_|has_)?(?:non_?)?refundab\w*$|^cancellation(?:_(?:polic(?:y|ies)|terms?|until|deadline|fees?|window|rules?|charge))?$|^(?:free_)?cancel(?:_\w*)?_?(?:polic(?:y|ies)|until|deadline|fee|fees|terms|window|charge)\w*$|^free_?cancel\w*$|^refund_?(?:polic(?:y|ies)|until|deadline)\w*$/i

/** every member name inside an `interface X {…}` or `type X = {…}` block */
export function tsFields(src) {
  const out = []
  for (const m of src.matchAll(/\b(?:interface\s+\w+[^{]*|type\s+\w+\s*=\s*)\{/g)) {
    let depth = 1, i = m.index + m[0].length
    const start = i
    while (i < src.length && depth) { depth += src[i] === '{' ? 1 : src[i] === '}' ? -1 : 0; i++ }
    for (const mm of src.slice(start, i).matchAll(/(?:^|[;{\n])\s*(?:readonly\s+)?['"]?([A-Za-z_]\w*)['"]?\??\s*:\s*[^=]/g)) out.push(mm[1])
  }
  return out
}

test('the reader sees a field, and the name rule catches the class and nothing else', () => {
  assert.deepEqual(tsFields('export interface I {\n  id?: string\n  is_refundable: boolean\n}'), ['id', 'is_refundable'])
  assert.deepEqual(tsFields('type T = { a: number; cancellation_policy?: string }'), ['a', 'cancellation_policy'])
  for (const n of ['is_refundable', 'refundable', 'cancellation_policy', 'free_cancellation', 'cancel_deadline']) assert.match(n, TERM_FIELD)
  for (const n of ['cancelled', 'cancelled_at', 'booking_cancel', 'status', 'cancellation_id']) assert.doesNotMatch(n, TERM_FIELD)
})

test('424 · no type in the app holds a booking-term field', () => {
  const bad = SRC.flatMap(({ p, t }) => tsFields(t).filter((n) => TERM_FIELD.test(n)).map((n) => `${p}: ${n}`))
  assert.deepEqual(bad, [])
})

test('424 · no component composes a term (the deleted readers and sentences stay deleted)', () => {
  const COMPOSERS = ['termHead', 'TERM_LABEL', 'cancelBy(', 'by_words', 'only the airline can cancel', "can't be refunded", 'Cancellation deadline']
  const bad = SRC.flatMap(({ p, t }) => COMPOSERS.filter((c) => t.includes(c)).map((c) => `${p}: ${c}`))
  assert.deepEqual(bad, [])
})

test('423 · no screen says Refundable / Non-refundable / Free cancellation from a field of Sasha\'s', () => {
  const bad = SRC.filter(({ t }) => /['"`>]\s*(?:(?:Non-)?[Rr]efundable|[Ff]ree [Cc]ancellation)\s*['"`<]|\bis_refundable\b/.test(t)).map(({ p }) => p)
  assert.deepEqual(bad, [])
})
