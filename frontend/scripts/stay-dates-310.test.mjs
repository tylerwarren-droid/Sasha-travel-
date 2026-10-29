// Sasha 310 · a stay on the Plans card reads as AgAPI's record has it — check-in → check-out · nights — drawn as given, never worked out.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const cards = readFileSync(new URL('../app/components/cards/S2Cards.tsx', import.meta.url), 'utf8')

test('the Plans row draws a stay from its record: check-in → check-out · nights', () => {
  assert.match(cards, /\{stayWhen\(p\)\}\{p\.where/)
  assert.match(cards, /if \(!p\.check_out\) return fmtWhen\(p\.when\)/)
  assert.match(cards, /\$\{fmtWhen\(p\.when\)\} → \$\{fmtWhen\(p\.check_out\.slice\(0, 10\)\)\}\$\{n\}/)
})

test('nothing about the stay is computed on the page (no date arithmetic on nights)', () => {
  const fn = cards.slice(cards.indexOf('export function stayWhen'), cards.indexOf('const PLAN_ICON'))
  assert.doesNotMatch(fn, /setDate|getDate\(\)\s*\+|86400|\* 24/)
})
