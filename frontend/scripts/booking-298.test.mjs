// Sasha 298 · READY FOR TYLER'S THREE REAL BOOKINGS — the page's half: the hand-over card says what its one tap does, and each turn
// carries the browser's language (297's question is picked by it, as "Aquí sigo." is here).
//   node --test scripts/booking-298.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')

test('298 · the hand-over card: its heading and its next step from where the button goes — never "their page" over a WhatsApp send', () => {
  assert.match(app, /<Box k="One tap left" h=\{handoverWords\(c\.url\)\.h\}>/)
  assert.match(app, /<div data-handover-next[^>]*>\{handoverWords\(c\.url\)\.next\}<\/div>/)
  assert.doesNotMatch(app, /<Box k="One tap left" h="Finish it on their page">/)
  const fn = app.slice(app.indexOf('const handoverWords = '), app.indexOf('/** Sasha 298 · the browser'))
  assert.match(fn, /wa\\\.me/)
  assert.match(fn, /you press send/)
  assert.match(fn, /you press Book there/)
})

test('298 · every turn carries the page\'s language', () => {
  assert.match(app, /channel: m\.channel, lang: pageLang\(\),/)
  assert.match(app, /const pageLang = \(\): string => \{ try \{ return navigator\.language \|\| 'en' \} catch \{ return 'en' \} \}/)
})
