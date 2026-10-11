// Sasha 241 · who is acting: a real signed-in account wins over the founder cookie; an automatic guest never does.
import test from 'node:test'
import assert from 'node:assert/strict'
import { decide, badge, isAutoGuest } from '../lib/acting-rule.mjs'

test('a real sign-in wins over the founder cookie (found in 240: the cookie overrode it)', () => {
  assert.equal(decide({ hasSession: true, guestEmail: 'tylerwarren+eu234@gmail.com', founderCookie: true }), 'user')
})
test('the founder cookie wins over the automatic browser guest (every browser has one)', () => {
  assert.equal(decide({ hasSession: true, guestEmail: 'guest-79ca220e4786@guests.kanoe.ai', founderCookie: true }), 'founder')
})
test('alone, each is itself; nobody is null', () => {
  assert.equal(decide({ founderCookie: true }), 'founder')
  assert.equal(decide({ hasSession: true, guestEmail: 'guest-x@guests.kanoe.ai' }), 'guest')
  assert.equal(decide({ hasSession: true, guestEmail: 'a@b.com' }), 'user')
  assert.equal(decide({}), null)
})
test('the badge names who is acting', () => {
  assert.equal(badge('user', 'tylerwarren+eu234@gmail.com'), 'Signed in as tylerwarren+eu234@gmail.com')
  assert.equal(badge('founder'), 'Founder: Tyler')
  assert.equal(badge('guest', 'guest-x@guests.kanoe.ai'), 'Guest')
  assert.ok(isAutoGuest('GUEST-1@GUESTS.KANOE.AI'))
})

test('Sasha 242 · per-person storage goes when the person acting changes, not on a first visit', async () => {
  const { whoKey, changed, PER_PERSON_LOCAL } = await import('../lib/acting-rule.mjs')
  const a = whoKey('user', 'Tylerwarren+EU234@gmail.com'), b = whoKey('user', 'someone@else.com')
  assert.equal(a, 'user:tylerwarren+eu234@gmail.com')
  assert.ok(changed(a, b))
  assert.ok(changed(whoKey('founder'), a))
  assert.ok(!changed(a, a))
  assert.ok(!changed(null, a))              // first visit: nothing to clear
  assert.ok(PER_PERSON_LOCAL.includes('sasha_last_session'))
})
