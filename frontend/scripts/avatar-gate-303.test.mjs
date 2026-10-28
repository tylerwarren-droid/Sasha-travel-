// Sasha 303 · ONE GATE for her live face (HeyGen LiveAvatar bills by the minute) — the page's half. The backend's
// app/avatar_gate.py decides, holds and closes every session; here: the ONE function that mints a session token, called by ONE
// route and only after the gate's yes; no other code in the app mints one; the page opens her face on his tap only (never on load),
// keeps no idle timer of its own, and tells the gate when it is hidden or closed.
//   node --test scripts/avatar-gate-303.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname
const read = (p) => readFileSync(join(ROOT, p), 'utf8')
const files = []
const walk = (d) => {
  for (const n of readdirSync(d)) {
    if (['node_modules', '.next', 'public', 'scripts'].includes(n)) continue
    const p = join(d, n)
    if (statSync(p).isDirectory()) walk(p)
    else if (/\.(ts|tsx|js|mjs)$/.test(n)) files.push(relative(ROOT, p))
  }
}
walk(ROOT)

test('303 · the whole class: sessions/token is minted in ONE place, imported by ONE route', () => {
  const minting = files.filter(f => read(f).includes('sessions/token'))
  assert.deepEqual(minting, ['lib/avatar-mint.ts'])
  const importers = files.filter(f => /from '@\/lib\/avatar-mint'/.test(read(f)))
  assert.deepEqual(importers, ['app/api/s2-avatar/token/route.ts'])
  const s2 = read('app/api/s2-avatar/token/route.ts')
  assert.ok(s2.indexOf('/api/avatar/open') < s2.indexOf('mintSession('), 'the gate is asked BEFORE anything is minted')
  assert.ok(s2.indexOf('mintSession(') < s2.indexOf('/api/avatar/opened'), 'the token goes to the gate at once')
  assert.ok(!files.some(f => f.startsWith('app/') && /sessions\/(start|stop|keep-alive)/.test(read(f))), 'no page calls the API itself')
})

test('303 · the legacy token routes (/vietnam, /next, the site root) mint nothing: a still', () => {
  for (const f of ['app/api/heygen/token/route.ts', 'app/api/heygen/token/phuquoc/route.ts']) {
    const s = read(f)
    assert.ok(!s.includes('liveavatar.com'), f)
    assert.ok(s.includes("rule: 'avatar_closed'"), f)
  }
  const av = read('app/components/SashaAvatar.tsx')
  assert.ok(av.includes("'avatar_closed'") && av.includes("status === 'still'"), 'a refused avatar shows her still, not an error')
})

test('303 · /s2 opens her face on his tap only, keeps no idle timer, and tells the gate when hidden or closed', () => {
  const hello = read('app/s2/S2Hello.tsx')
  assert.ok(!hello.includes('FACE_IDLE_S'), 'no page idle timer: the gate closes a quiet face')
  assert.ok(!/early\.current = \{ p: startFace/.test(hello), 'never started on load')
  assert.ok(!hello.includes('?? startFace(v)'), 'never started by the arrival')
  assert.equal((hello.match(/startFace\(/g) || []).length, 3, 'defined once; started by the tap (tapFace) and her face tapped back (faceBack)')
  assert.ok(hello.includes("JSON.stringify({ why: 'tap' })"))
  const gate = read('lib/avatar-session.ts')
  assert.ok(gate.includes("addEventListener('visibilitychange'") && gate.includes("'hidden'"))
  assert.ok(gate.includes("addEventListener('pagehide'") && gate.includes('sendBeacon'))
  assert.ok(!/setTimeout\([^)]*close/.test(gate), 'no limit decided on the page')
})
