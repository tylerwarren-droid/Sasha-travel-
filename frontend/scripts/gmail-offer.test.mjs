// Sasha 244 · /you doesn't push a Gmail someone doesn't have.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { gmailOffer, isGmailAddress, quietLine } from '../lib/gmail-offer.mjs'

test('an iCloud sign-in (Jon) gets the quiet line, not the connect form', () => {
  assert.equal(gmailOffer({ email: 'jonc@icloud.com', connected: false, expired: false, opened: false }), 'quiet')
  assert.match(quietLine('jonc@icloud.com'), /^You signed in with an iCloud address\. Connect Gmail only if you have a Gmail account/)
  assert.doesNotMatch(quietLine('jonc@icloud.com'), /jonc/)
})

test('a Gmail sign-in, a connected or expired Gmail, or "I have a Gmail account" → the full form', () => {
  assert.equal(gmailOffer({ email: 'tylerwarren@gmail.com' }), 'full')
  assert.equal(gmailOffer({ email: 'x@googlemail.com' }), 'full')
  assert.equal(gmailOffer({ email: 'jonc@icloud.com', connected: true }), 'full')
  assert.equal(gmailOffer({ email: 'jonc@icloud.com', expired: true }), 'full')
  assert.equal(gmailOffer({ email: 'jonc@icloud.com', opened: true }), 'full')
  assert.equal(gmailOffer({ email: undefined }), 'full')   // the founder: as before
})

test('only gmail.com / googlemail.com count', () => {
  assert.equal(isGmailAddress('jon@kanoe.ai'), false)
  assert.equal(isGmailAddress('a@gmail.co'), false)
  assert.match(quietLine('jon@kanoe.ai'), /a kanoe\.ai address/)
})
