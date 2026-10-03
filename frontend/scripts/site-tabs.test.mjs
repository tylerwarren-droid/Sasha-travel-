// Sasha 123 · the new project.kanoe.ai (kanoe-site-scope.md §9.6), read as SOURCE — no build, no network, no dependency.
//   cd frontend && npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

const root = new URL('..', import.meta.url).pathname
const read = (p) => readFileSync(join(root, p), 'utf8')
const CONTENT = ['agapi', 'sasha', 'ad', 'campusme', 'relocation', 'spain'].map((n) => [n, read(`app/(site)/content/${n}.ts`)])

test('1 · the menu has exactly the six tabs, and no archive page', () => {
  const nav = read('app/components/site/SiteNav.tsx')
  const hrefs = [...nav.matchAll(/href: '([^']+)'/g)].map((m) => m[1])
  assert.deepEqual(hrefs, ['/', '/sasha', '/applied-diligence', '/campusme', '/relocation', '/spain-services'])
  for (const gone of ['/archive', '/deck', '/tdm', '/data-strategy', '/walkthrough', '/demo']) assert.ok(!hrefs.includes(gone), gone)
})

test('2 · every claim line carries a status and its evidence; exactly three lines per tab', () => {
  for (const [n, src] of CONTENT) {
    const lines = [...src.matchAll(/\{ status: '(proven|reported|concept)', evidence: '(?:[^'\\]|\\.)+',\s*\n?\s*text: /g)]
    assert.equal(lines.length, 3, n)
    assert.match(src, /statusLine: '/, n)
  }
})

test('3 · every demo carries a label', () => {
  for (const [n, src] of CONTENT) assert.match(src, /demo: \{ kind: '(live|click-through|concept)'/, n)
  assert.match(read('app/(site)/content/spain.ts'), /demo: \{ kind: 'concept'/)   // CONCEPT only
})

test('6 · the archive pages are noindex; the new pages are not', () => {
  for (const p of ['app/archive/page.tsx', 'app/deck/page.tsx', 'app/walkthrough/page.tsx', 'app/tdm/page.tsx', 'app/data-strategy/page.tsx', 'app/demo/page.tsx'])
    assert.match(read(p), /robots: \{ index: false/, p)
  for (const p of ['app/page.tsx', 'app/sasha/page.tsx', 'app/applied-diligence/page.tsx', 'app/campusme/page.tsx', 'app/relocation/page.tsx', 'app/spain-services/page.tsx'])
    assert.doesNotMatch(read(p), /index: false/, p)
})

test('7 · the content never says what isn\'t so', () => {
  const banned = ['Sasha runs on AgAPI', 'four working agents', 'his output is evidence', 'Working today: Magellan', 'crypto', 'stablecoin', 'Amadeus']
  for (const [n, src] of CONTENT) for (const b of banned) assert.ok(!src.toLowerCase().includes(b.toLowerCase()), `${n}: ${b}`)
  // ⛔ relocation: never a count split (kanoe-site-scope.md §11)
  assert.doesNotMatch(read('app/(site)/content/relocation.ts'), /\b(31\s*\/\s*8|44\s*\/\s*1\s*\/\s*51|43\s*\/\s*8\s*\/\s*45)\b/)
})

test('the archive: the old home page moved verbatim, the Teaser tab points at it, the banner is on, the footer links it', () => {
  const archive = read('app/archive/page.tsx')
  assert.match(archive, /<PortalShell>\s*<Teaser \/>\s*<\/PortalShell>/)
  assert.match(read('app/components/portal/PortalNav.tsx'), /\{ href: '\/archive', label: 'Teaser' \}/)
  assert.match(read('app/components/portal/PortalShell.tsx'), /<ArchiveBanner \/>/)
  assert.match(read('app/components/site/SiteShell.tsx'), /href="\/archive">Original vision \(archive\) →/)
  assert.match(read('app/components/site/SiteShell.tsx'), /© 2026 Kanoe Technologies SL · NIF B23942923 · Calle Padre Damián 41, 28036 Madrid/)
})

test('the team listing is untouched (founder, EU 135)', () => {
  const deck = read('app/components/portal/Deck.tsx')
  for (const name of ['Tyler Warren', 'Josh Rosenthal', 'Gaston Tchicourel']) assert.ok(deck.includes(name), name)
})

test('CampusMe and Relocation link to the CR tab\'s showcase pages, with the fictional person said', () => {
  assert.match(read('app/(site)/content/campusme.ts'), /\/campus-handover\/vuvpvu6fG71M5b_rxtEsag/)
  assert.match(read('app/(site)/content/campusme.ts'), /read live on 3 Oct 2026 — the student is fictional/)
  assert.match(read('app/(site)/content/relocation.ts'), /\/relocation-file\/KZjdXS_8HLk5I9nW76SW_A/)
  assert.match(read('app/(site)/content/relocation.ts'), /The applicant shown here is fictional/)
  assert.ok(existsSync(join(root, 'public/data/austen/submit-www.handelsregister.de-2026-09-23.json')))
})
