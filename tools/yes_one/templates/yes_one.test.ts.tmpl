/**
 * yes_one · THE conformance set for yes_one.ts (generated; DO NOT EDIT — tools/yes_one/generate.py). The same conformance.json runs
 * against yes_one.py (test_yes_one.py).   node --experimental-strip-types yes_one.test.ts
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Y from './yes_one.ts'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const C: any = JSON.parse(readFileSync(new URL('./conformance.json', import.meta.url), 'utf8'))
const ACCOUNT = 'acct_flow', PERSON = 'usr_flow', AT = '2026-10-10T10:00:00Z'
const PAYLOAD = { total_minor: 89000, currency: 'EUR', offer: 'off_1' }
const LINES = ['Iberia IB6061 Madrid → Hanoi, 2 Nov', 'Total EUR 890.00']

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function flow(c: any) {
  const op = c.operation || 'trip.complete'
  const rb = Y.readBack(ACCOUNT, 'int_flow', op, LINES, PAYLOAD, PERSON, 't1', AT)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const apv: any = Y.approval(rb, c.approved_by || PERSON, c.approved_turn, c.approved_at, { said: c.said ?? null, channel: c.channel || 'sasha_chat' })
  if (c.consumed) apv.state = 'consumed'
  const cur = { intent_id: 'int_flow', operation: op, lines: c.act_lines || LINES, payload: c.act_payload || PAYLOAD }
  return Y.checkAct(rb, apv, cur, c.act_at, { lang: 'lang' in c ? c.lang : 'en' })
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function idempotency(c: any): any[] {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const L = new Y.Ledger(), out: any[] = []
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let pending: any = null
  c.steps.forEach((s: any, i: number) => {   // eslint-disable-line @typescript-eslint/no-explicit-any
    if (s.caller === 'anonymous') { out.push({ status: 401, code: 'unauthenticated', replayed: false, key_store_touched: false }); return }
    const acct = s.caller.split('·')[0], op = s.operation || 'trip.complete'
    if (op === 'acts.status') {
      const p = pending
      L.resolve(p.acct, p.op, p.key, 201, { ok: true, result: { outcome: 'CONFIRMED', n: p.n } }, { intentId: p.intent, actId: p.act })
      out.push({ status: 200, outcome: 'CONFIRMED' }); return
    }
    if (s.upstream === 'rate_limited_by_us') { out.push({ status: 429, code: 'rate_limited', stored: false }); return }
    const intent = op === 'trip.complete' ? (s.input || {}).hold_id : undefined
    const b = L.begin(acct, op, s.idempotency_key, s.input, intent)
    if (b.do === 'refuse') { out.push({ status: b.status, code: b.code, upstream_calls: 0, ...(b.details ? { details: b.details } : {}) }); return }
    if (b.do === 'replay') {
      out.push({ status: b.status, ok: b.body.ok, replayed: true, upstream_calls: 0, charged: false, body: b.body, ...(b.body.ok ? {} : { code: b.body.error.code }) }); return
    }
    const act = `act_${i}_${acct}`, key = s.idempotency_key, up = s.upstream
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let body: any, st: number
    if (up === 'confirmed' || up === 'cancelled') { body = { ok: true, result: { act_id: act, n: `${acct}:${i}` } }; st = 201 }
    else if (up === 'slow_confirmed') { out.push({ status: 201, ok: true, upstream_calls: 1, _finish: [acct, op, key, 201, { ok: true, result: { act_id: act } }, intent, act] }); return }
    else if (up === 'refused') { body = { ok: false, error: { code: 'upstream_refused' } }; st = 422 }
    else if (up === 'unreachable') { body = { ok: false, error: { code: 'upstream_unreachable' } }; st = 503 }
    else if (up === 'timeout_after_send') { body = { ok: false, error: { code: 'outcome_unknown', details: { act_id: act } } }; st = 502; pending = { acct, op, key, intent, act, n: `${acct}:${i}` } }
    else throw new Error(up)
    L.finish(acct, op, key, st, body, { intentId: intent, actId: act })
    const row = L.store.get(`${acct}\u0000${op}\u0000${key}`)
    out.push({ status: st, ok: body.ok, replayed: false, upstream_calls: 1, charged: !!body.ok, body, stored: !!row && row.state === 'done', ...(body.ok ? {} : { code: body.error.code }), ...(!body.ok && body.error.details ? { details: body.error.details } : {}) })
  })
  for (const o of out) if (o._finish) { const [a, op, k, st, body, intent, act] = o._finish; delete o._finish; L.finish(a, op, k, st, body, { intentId: intent, actId: act }) }
  return out
}

test('contract version', () => assert.equal(Y.CONTRACT_VERSION, C.contract_version))
test('approval vectors', () => {
  for (const c of C.approval) assert.deepEqual(Y.decide(c), [c.expect.decision, c.expect.void_reason], `${c.id}: ${c.description}`)
})
test('explicit-yes vectors', () => {
  for (const c of C.explicit_yes) assert.equal(Y.explicitYes(c.said, c.lang, c.act_kind ?? null), c.explicit_yes, c.said)
})
test('canonical vectors', () => {
  for (const c of C.canonical) {
    if (c.expect === 'refused') assert.throws(() => Y.canonical(JSON.parse(c.input_json)), Y.Refused, c.id)
    else { assert.equal(Y.canonical(c.input), c.canonical, c.id); assert.equal(Y.sha256(c.input), c.sha256, c.id) }
  }
})
test('idempotency vectors', () => {
  for (const c of C.idempotency) {
    const got = idempotency(c)
    c.steps.forEach((s: any, i: number) => {   // eslint-disable-line @typescript-eslint/no-explicit-any
      const e = s.expect, g = got[i]
      for (const k of ['status', 'code', 'ok', 'replayed', 'upstream_calls', 'stored', 'outcome']) if (k in e) assert.deepEqual(g[k], e[k], `${c.id} step ${i + 1} ${k}`)
      if (e.same_result_as_step) assert.deepEqual(g.body, got[e.same_result_as_step - 1].body)
      if (e.result_differs_from_step) assert.notDeepEqual(g.body, got[e.result_differs_from_step - 1].body)
      if (e.details && e.details.act_id) assert.ok(g.details && g.details.act_id, `${c.id} step ${i + 1} act_id`)
    })
  }
})
test('flow: read-back → a later-turn yes → the act', () => {
  for (const c of C.flow) assert.deepEqual(flow(c), c.expect, `${c.id}: ${c.says}`)
})
