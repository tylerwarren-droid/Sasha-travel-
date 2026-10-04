// Sasha 142 · the /agapi hub (EU 152's pitches) and the root, read as SOURCE — no build, no network, no dependency.
//   cd frontend && npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const root = new URL('..', import.meta.url).pathname
const read = (p) => readFileSync(join(root, p), 'utf8')
const content = read('app/agapi/content.ts')
const body = content.slice(content.indexOf('export const PITCHES'))
const pitches = body.split(/\n  \{\n    key: /).slice(1)

test('the root is the Sasha Vietnam site; the hub is /agapi', () => {
  assert.match(read('app/page.tsx'), /import VietnamPage from '\.\/vietnam\/page'/)
  assert.match(read('app/page.tsx'), /export default VietnamPage/)
  assert.match(read('app/agapi/page.tsx'), /<Hub \/>/)
})

test('the five products, in the founder\'s order, each with its copy in or held', () => {
  const names = [...body.matchAll(/^    key: '[^']+', name: '([^']+)'/gm)].map((m) => m[1])
  assert.deepEqual(names, ['Sasha (Vietnam)', 'Applied Diligence', 'CampusMe', 'RelocateMe', 'EspañaMe'])
  for (const p of pitches) assert.match(p, /ready: (true|false)/)
  assert.match(read('app/agapi/Hub.tsx'), /PITCHES\.filter\(\(p\) => p\.ready\)/)   // a held tab is never shown
})

test('no placeholder is ever published', () => {
  for (const bad of ['TODO', 'TBD', 'lorem', 'placeholder', 'coming soon', 'XXX']) {
    assert.ok(!body.toLowerCase().includes(bad.toLowerCase()), bad)
  }
})

test('every figure carries a mark, and every sourced or vendor figure a source URL', () => {
  const figs = [...body.matchAll(/\{ row: '([^']+)'[\s\S]*?marks: \[([^\]]+)\][\s\S]*?sources: \[([\s\S]*?)\] \}/g)]
  assert.ok(figs.length >= 20, `figures found: ${figs.length}`)
  for (const [, row, marks, sources] of figs) {
    const ms = [...marks.matchAll(/'([SVEF])'/g)].map((m) => m[1])
    assert.ok(ms.length > 0, `${row}: no mark`)
    if ((ms.includes('S') || ms.includes('V')) && !ms.includes('E') && !ms.includes('F')) assert.match(sources, /S\('https:\/\//, `${row}: no source`)
    if (/^SOM/.test(row)) assert.deepEqual(ms, ['F'], `${row}: a SOM is a founder assumption`)
  }
})

test('a SOM is its variables, never a number', () => {
  for (const m of body.matchAll(/row: 'SOM', figure: '([^']+)'/g)) assert.match(m[1], /^\[/, m[1])
})

test('the demo links go to the CR tab\'s previews and the WhatsApp words', () => {
  for (const slug of ['campusme', 'relocateme', 'espaname']) assert.match(body, new RegExp(`href: '/preview/${slug}'`))
  for (const w of ['relocate', 'campus', 'españa', 'diligence']) assert.ok(read('app/agapi/content.ts').includes(`type ${w}`) || body.includes(`Type ${w}`), w)
})

test('the hub never says what isn\'t so', () => {
  for (const b of ['Sasha runs on AgAPI', 'four working agents', 'crypto', 'stablecoin', 'Amadeus']) assert.ok(!content.toLowerCase().includes(b.toLowerCase()), b)
  assert.match(body, /\+84 calls aren’t connected yet/)
  assert.match(body, /No revenue/)
})

test('no personal email or phone number on the hub', () => {
  for (const f of ['app/agapi/content.ts', 'app/agapi/Hub.tsx', 'app/agapi/page.tsx']) {
    assert.doesNotMatch(read(f), /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/, f)
    assert.doesNotMatch(read(f), /\+\d{2}[\s\d]{8,}/, f)
  }
})
