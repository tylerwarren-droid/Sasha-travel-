// Sasha 249 · ONE IDENTITY (one-truth-spec §1.1–1.2, T1): the badge renders whoami's `acting`, never the email suffix; one
// agentHeaders(acting) builds the identity headers for all three proxies; no fixed person stands in as a fallback.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { actingOf, badgeFor, badge } from '../lib/acting-rule.mjs'
import { headersFor, clientIp } from '../lib/agent-headers.mjs'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = (p) => readFileSync(join(ROOT, p), 'utf8')

test('T1 · the badge is whoami\'s acting — the email never decides it', () => {
  // a real sign-in whose address happens to be on guests.kanoe.ai is still the account acting
  assert.equal(badgeFor({ who: 'guest', acting: 'user', email: 'x@guests.kanoe.ai' }), 'Signed in as x@guests.kanoe.ai')
  // the automatic guest is a Guest whatever its address says
  assert.equal(badgeFor({ who: 'guest', acting: 'guest', email: 'someone@gmail.com' }), 'Guest')
  // `who: 'founder'` without acting names nobody here: acting is the one answer
  assert.equal(badgeFor({ who: 'founder' }), 'Guest')
  assert.equal(badgeFor({ who: 'founder', acting: 'founder' }), badge('founder'))
  for (const w of [null, undefined, {}, { acting: 'admin' }, { acting: 7 }]) assert.equal(actingOf(w), null)
})

test('T1 · no page re-derives who is acting from the email suffix', () => {
  for (const p of ['app/components/SignedInLine.tsx', 'app/components/KeepAcrossDevices.tsx', 'app/api/guest/email/route.ts']) {
    const s = src(p)
    assert.ok(!/endsWith\(\s*['"]@guests\.kanoe\.ai['"]\s*\)/.test(s), `${p} decides from the email suffix`)
  }
  assert.match(src('app/components/SignedInLine.tsx'), /badgeFor\(who\)/)
  assert.match(src('app/api/guest/email/route.ts'), /actingAs\(\)/)
})

test('T1 · useSignedIn and guest-auth ask whoami', () => {
  const s2 = src('app/s2/S2App.tsx')
  const fn = s2.slice(s2.indexOf('function useSignedIn'), s2.indexOf('function useSignedIn') + 600)
  assert.match(fn, /\/api\/auth\/whoami/)
  assert.ok(!/sasha-agent\/activity/.test(fn), 'useSignedIn is an activity ping again')
  assert.match(src('lib/guest-auth.ts'), /\/api\/auth\/whoami/)
})

test('one agentHeaders(acting): the three proxies build no identity header of their own', () => {
  for (const p of ['lib/agent-auth.ts', 'app/api/booking-proxy/[...path]/route.ts', 'app/api/sasha/[...path]/route.ts']) {
    const s = src(p)
    assert.ok(!/['"]x-sasha-session['"]\s*:/.test(s), `${p} builds x-sasha-session itself`)
    assert.ok(!/Bearer \$\{/.test(s), `${p} builds the bearer header itself`)
    if (!p.startsWith('lib/')) assert.match(s, /agentHeaders\(acting/, `${p} does not call agentHeaders(acting)`)
  }
})

test('headersFor: nobody, the founder (only with the key), a signed-in account', () => {
  assert.equal(headersFor(null, { key: 'k' }), null)
  assert.equal(headersFor({ kind: 'founder' }, { key: '' }), null)                       // no key: the founder names nobody
  assert.deepEqual(headersFor({ kind: 'founder' }, { key: 'k', clientKey: 'c', ip: '1.2.3.4' }),
    { 'x-sasha-session': 'founder', 'x-sasha-booking-key': 'k', 'x-sasha-client-ip': '1.2.3.4', 'X-Client-Key': 'c' })
  assert.deepEqual(headersFor({ kind: 'user', accessToken: 't' }, { key: 'k', clientKey: 'c', ip: '1.2.3.4' }),
    { authorization: 'Bearer t', 'X-Client-Key': 'c' })                                  // never the booking key, never his ip
  assert.deepEqual(headersFor({ kind: 'guest', accessToken: 't' }), { authorization: 'Bearer t' })
  assert.equal(headersFor({ kind: 'guest', accessToken: '' }), null)
  const h = new Map([['x-forwarded-for', ' 9.9.9.9 , 10.0.0.1'], ['x-real-ip', '8.8.8.8']])
  assert.equal(clientIp({ get: (k) => h.get(k) ?? null }), '9.9.9.9')
  assert.equal(clientIp({ get: (k) => (k === 'x-real-ip' ? '8.8.8.8' : null) }), '8.8.8.8')
})

test('no fixed person as a fallback: CURRENT_USER is gone, YouPanel has no "Jon Peters" address, /next no demo profile', () => {
  assert.ok(!existsSync(join(ROOT, 'lib/currentUser.ts')))
  assert.ok(!/CURRENT_USER/.test(src('app/components/workspace/YouPanel.tsx')))
  assert.ok(!/DEMO_USER|Jon Peters/.test(src('app/next/page.tsx')))
  assert.ok(!/11111111-1111-4111-8111-111111111111/.test(src('app/components/workspace/YouPanel.tsx')))
})
