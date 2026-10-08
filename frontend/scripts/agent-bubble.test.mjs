// Sasha 212 E · never an empty bubble (lib/agent-bubble.mjs, used by SashaChat's agentTurn)
import test from 'node:test'
import assert from 'node:assert/strict'
import { placeReply, visible } from '../lib/agent-bubble.mjs'

const said = [{ role: 'user', content: 'Flying from London.' }]

test('a turn that starts with a tool adds no bubble until her first words', () => {
  assert.deepEqual(placeReply(said, '', true), said)          // the tool runs: nothing on screen but the spinner
  assert.deepEqual(placeReply(said, '   ', true), said)
  const one = placeReply(said, "I've put a trip together for your consideration.", true)
  assert.equal(one.length, 2)
  assert.equal(one[1].role, 'assistant')
})

test('later words replace the same bubble, never a second one', () => {
  const one = placeReply(said, 'First.', true)
  const two = placeReply(one, 'First. Then more.', false)
  assert.equal(two.length, 2)
  assert.equal(two[1].content, 'First. Then more.')
})

test('the chat never renders a message without words', () => {
  assert.equal(visible({ role: 'assistant', content: '' }), false)
  assert.equal(visible({ role: 'assistant', content: '  ' }), false)
  assert.equal(visible({ role: 'user', content: '' }), false)
  assert.equal(visible({ role: 'assistant', content: 'Hello' }), true)
})
