/**
 * yes_one — THE ONE YES RULE, generated from the AgAPI 1.3 contract. DO NOT EDIT: regenerate with tools/yes_one/generate.py.
 *
 * contract: AgAPI 1.3 (EU) — operations.json b1d2673c5c7a, vectors/approval-language.json b4992034e275, vectors/approval-language-acts.json e8c8c2edc71e, vectors/approval.json 103eddeff299, vectors/explicit-yes.json 4ee8c822a610, vectors/canonical.json 2ce5e4853c1f, vectors/idempotency.json 532032324906
 *
 * Every act that moves money or sends something: a READ-BACK (exact lines + payload, hashed) → the person's YES in a LATER turn (AP3;
 * an explicit yes, AP6, server-side, never a model) → ONE idempotent act (§7). The same rules as yes_one.py, from the same contract;
 * both pass the same conformance set (conformance.json).
 */
import { createHash } from 'node:crypto'

export const CONTRACT_VERSION = '1.3'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const CONTRACT: any = JSON.parse(String.raw`{"acts": {"cancel": {"en": {"exempt_negations": ["cancel"]}, "es": {"exempt_negations": ["cancela"]}}}, "acts_rule_version": "1.1", "approval_operations": ["trip.complete", "trip.cancel", "messages.send_email", "messages.send_whatsapp", "subscriptions.cancel"], "language_rule_version": "1.0", "languages": {"en": {"affirmatives": ["yes", "yeah", "yep", "yup", "sure", "definitely", "absolutely", "go ahead", "do it", "please do", "book it", "book the trip", "book my trip", "book our trip", "confirm", "let's do it", "lets do it", "let's book", "lets book"], "fillers": ["ok", "okay", "right", "so", "then", "great", "perfect", "lovely", "sasha"], "negations": ["no", "not", "don't", "dont", "do not", "wait", "hold on", "later", "cancel", "stop", "maybe", "never", "nope"], "questions_and_requests": ["what", "how", "which", "when", "where", "why", "who", "options", "terms", "policy", "find", "search", "show me", "look up", "tell me", "can you", "could you", "would you", "is it", "are there", "list"]}, "es": {"affirmatives": ["sí", "si", "claro", "adelante", "hazlo", "resérvalo", "reservalo", "confirma", "confirmo", "de acuerdo", "vale", "por supuesto", "venga"], "fillers": ["bueno", "pues", "perfecto", "genial", "sasha", "entonces", "ok", "okay"], "negations": ["no", "espera", "todavía no", "luego", "después", "despues", "cancela", "para", "quizás", "quizas", "quizá", "quiza", "tal vez", "nunca"], "questions_and_requests": ["qué", "cómo", "cuál", "cuáles", "cuándo", "dónde", "por qué", "opciones", "condiciones", "política", "busca", "buscar", "búscame", "muéstrame", "enséñame", "dime", "puedes", "podrías"]}}, "order": ["approval_not_found", "approval_untrusted_origin", "approval_consumed", "approval_same_turn", "no_explicit_yes", "approval_expired", "approval_void:irreversible_batch", "approval_void:intent_changed", "approval_void:payload_changed", "approval_void:read_back_changed", "valid"], "version": "1.3"}`)
export const ORDER: string[] = CONTRACT.order
export const READ_BACK_TTL_MIN = 30, APPROVAL_TTL_MIN = 15, IRREVERSIBLE_TTL_MIN = 15
export const TRUSTED_CHANNELS = ['link', 'sdk', 'sasha_voice', 'sasha_chat']
export const STORE_FOR_REPLAY = ['upstream_refused', 'approval_void', 'approval_expired', 'approval_consumed', 'no_explicit_yes', 'already_completed', 'invalid_input']
const KEY_RE = /^[A-Za-z0-9_-]{16,128}$/
const MAX_INT = 2 ** 53 - 1
const OBJ_KEY = /^[a-z0-9_]+$/

export class Refused extends Error {}

// ── Part 1 §4 canonical JSON and hashes ──────────────────────────────────────────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function check(v: any): void {
  if (v === null || typeof v === 'boolean') return
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) throw new Refused('non-finite number')
    if (!Number.isInteger(v)) throw new Refused('float')
    if (Math.abs(v) > MAX_INT) throw new Refused('integer out of range')
    return
  }
  if (typeof v === 'string') {
    for (let i = 0; i < v.length; i++) {
      const c = v.charCodeAt(i)
      if (c >= 0xd800 && c <= 0xdbff) { const d = v.charCodeAt(i + 1); if (d >= 0xdc00 && d <= 0xdfff) { i++; continue } throw new Refused('lone surrogate') }
      if (c >= 0xdc00 && c <= 0xdfff) throw new Refused('lone surrogate')
    }
    return
  }
  if (Array.isArray(v)) { v.forEach(check); return }
  if (typeof v === 'object') { for (const k of Object.keys(v)) { if (!OBJ_KEY.test(k)) throw new Refused('key charset'); check(v[k]) } return }
  throw new Refused(`type ${typeof v}`)
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ser(v: any): string {
  if (v === null || typeof v !== 'object') return JSON.stringify(v === -0 ? 0 : v)
  if (Array.isArray(v)) return '[' + v.map(ser).join(',') + ']'
  return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + ser(v[k])).join(',') + '}'
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function canonical(v: any): string { check(v); return ser(v) }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function sha256(v: any): string { return 'sha256:' + createHash('sha256').update(canonical(v), 'utf8').digest('hex') }
export function readBackSha256(account: string, intentId: string, operation: string, lines: string[], payloadSha256: string): string {
  return sha256({ account, intent_id: intentId, operation, lines, payload_sha256: payloadSha256 })
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function requestSha256(operation: string, input: any): string { return sha256({ operation, input }) }

// ── AP6 the explicit yes (server-side, never a model) ────────────────────────────────────────────────────────────────
const W = '[\\p{L}\\p{N}\\p{M}_]'
function normSaid(s: string, apostrophe = ''): string {
  let t = s.normalize('NFC').toLowerCase()
  t = t.replace(/['‘’]/g, apostrophe)
  t = t.replace(/[¡¿!?.,;:"“”()—–]/g, ' ')
  return t.replace(/\s+/g, ' ').trim()
}
function esc(s: string): string { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') }
function exempt(kind: string | null | undefined, lang: string): Set<string> {
  return new Set(kind ? (((CONTRACT.acts[kind] || {})[lang] || {}).exempt_negations || []) : [])
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function vetoed(said: string, L: any, ex: Set<string>): boolean {
  const forms = [normSaid(said || ''), normSaid(said || '', ' ')]
  const words: string[] = [...L.negations.filter((n: string) => !ex.has(n)), ...(L.questions_and_requests || [])]
  return words.some(w => forms.some(f => new RegExp(`(?<!${W})${esc(w)}(?!${W})`, 'u').test(f)))
}
export function explicitYes(said: string | null | undefined, lang = 'en', actKind: string | null = null): boolean {
  const L = CONTRACT.languages[lang]
  const t = normSaid(said || '')
  if (!t || vetoed(said || '', L, exempt(actKind, lang))) return false
  let rest = t, changed = true
  const fillers = [...L.fillers].sort((a: string, b: string) => b.length - a.length)
  while (changed) {
    changed = false
    for (const f of fillers) if (rest === f || rest.startsWith(f + ' ')) { rest = rest.slice(f.length).trim(); changed = true }
  }
  return [...L.affirmatives].sort((a: string, b: string) => b.length - a.length).some((a: string) => rest === a || rest.startsWith(a + ' '))
}
export function explicitYesAny(said: string | null | undefined, actKind: string | null = null): [boolean, string | null] {
  for (const code of Object.keys(CONTRACT.languages)) if (vetoed(said || '', CONTRACT.languages[code], exempt(actKind, code))) return [false, null]
  for (const code of Object.keys(CONTRACT.languages)) if (explicitYes(said, code, actKind)) return [true, code]
  return [false, null]
}
export function actKind(operation: string | null | undefined): string | null {
  return operation && (operation.split('.').pop() || '').startsWith('cancel') ? 'cancel' : null
}

// ── AP1–AP9 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
const T = (s: string) => Date.parse(s)
const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z')
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function decide(c: any, opts: { testMode?: boolean } = {}): [string, string | null] {
  const a = c.approval, rb = c.read_back, cur = c.current, now = T(c.now)
  const channels = [...TRUSTED_CHANNELS, ...(opts.testMode ? ['sandbox_simulated'] : [])]
  if (!a || a.account !== c.account) return ['approval_not_found', null]
  if (!channels.includes(a.device.channel) || a.approved_by !== rb.presented_to) return ['approval_untrusted_origin', null]
  if (a.device.channel === 'sdk' && !a.device.attestation) return ['approval_untrusted_origin', null]
  if (a.state === 'consumed') return ['approval_consumed', null]
  if (rb.presented_at == null || a.approved_turn_id === rb.presented_turn_id || !(T(a.approved_at) > T(rb.presented_at))) return ['approval_same_turn', null]
  if (a.method === 'voice' || (a.device.channel === 'sasha_chat' && a.said != null)) {
    const kind = c.act_kind || actKind(cur.operation)
    const ok = c.lang ? explicitYes(a.said, c.lang, kind) : explicitYesAny(a.said, kind)[0]
    if (!ok) return ['no_explicit_yes', null]
  }
  if (T(a.approved_at) > T(rb.expires_at) || now > T(a.expires_at)) return ['approval_expired', null]
  if (a.irreversible && (c.acts_in_request ?? 1) > 1) return ['approval_void', 'irreversible_batch']
  if (cur.intent_id !== a.intent_id) return ['approval_void', 'intent_changed']
  if (sha256(cur.payload) !== a.payload_sha256) return ['approval_void', 'payload_changed']
  if (readBackSha256(c.account, cur.intent_id, cur.operation, cur.lines, sha256(cur.payload)) !== a.read_back_sha256) return ['approval_void', 'read_back_changed']
  return ['valid', null]
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function readBack(account: string, intentId: string, operation: string, lines: string[], payload: any, presentedTo: string, presentedTurnId: string, now: string, irreversible = true) {
  const psha = sha256(payload)
  const ttl = irreversible ? Math.min(READ_BACK_TTL_MIN, IRREVERSIBLE_TTL_MIN) : READ_BACK_TTL_MIN
  return { account, intent_id: intentId, operation, lines: [...lines], payload_sha256: psha, read_back_sha256: readBackSha256(account, intentId, operation, [...lines], psha),
    presented_to: presentedTo, presented_at: now, presented_turn_id: presentedTurnId, expires_at: iso(T(now) + ttl * 60000), irreversible }
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function approval(rb: any, approvedBy: string, approvedTurnId: string, now: string, o: { said?: string | null; channel?: string; method?: string; attestation?: string } = {}) {
  const channel = o.channel || 'sasha_chat'
  return { account: rb.account, intent_id: rb.intent_id, read_back_sha256: rb.read_back_sha256, payload_sha256: rb.payload_sha256,
    method: o.method || (o.said != null && channel === 'sasha_voice' ? 'voice' : 'tap'), said: o.said ?? null, approved_by: approvedBy, approved_at: now,
    approved_turn_id: approvedTurnId, device: { channel, ...(o.attestation ? { attestation: o.attestation } : {}) },
    expires_at: iso(T(now) + APPROVAL_TTL_MIN * 60000), irreversible: rb.irreversible ?? true, state: 'valid' }
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function checkAct(rb: any, apv: any, current: any, now: string, o: { actsInRequest?: number; lang?: string | null; testMode?: boolean } = {}) {
  return decide({ account: rb.account, lang: o.lang ?? null, now, acts_in_request: o.actsInRequest ?? 1,
    read_back: { presented_to: rb.presented_to, presented_at: rb.presented_at, presented_turn_id: rb.presented_turn_id, expires_at: rb.expires_at },
    approval: apv, current }, { testMode: o.testMode })
}

// ── Part 1 §7 idempotency ────────────────────────────────────────────────────────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = { request_sha256: string; state: string; status: number | null; body: any }
export class MemoryStore {
  rows = new Map<string, Row>()
  intents = new Map<string, string>()
  get(s: string) { return this.rows.get(s) }
  put(s: string, r: Row) { this.rows.set(s, r) }
  delete(s: string) { this.rows.delete(s) }
  confirmedAct(account: string, intentId: string) { return this.intents.get(`${account}\u0000${intentId}`) }
  confirm(account: string, intentId: string, actId: string) { this.intents.set(`${account}\u0000${intentId}`, actId) }
}
export class Ledger {
  store: MemoryStore
  constructor(store?: MemoryStore) { this.store = store || new MemoryStore() }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  begin(account: string, operation: string, key: string | null | undefined, input: any, intentId?: string): any {
    if (!key) return { do: 'refuse', status: 400, code: 'idempotency_key_required' }
    if (!KEY_RE.test(key)) return { do: 'refuse', status: 400, code: 'invalid_request' }
    const scope = `${account}\u0000${operation}\u0000${key}`, rsha = requestSha256(operation, input)
    const row = this.store.get(scope)
    if (row) {
      if (row.request_sha256 !== rsha) return { do: 'refuse', status: 409, code: 'idempotency_conflict' }
      if (row.state === 'in_flight') return { do: 'refuse', status: 409, code: 'idempotency_in_flight', retry_after_s: 2 }
      return { do: 'replay', status: row.status, body: row.body }
    }
    if (intentId && this.store.confirmedAct(account, intentId)) return { do: 'refuse', status: 409, code: 'already_completed', details: { act_id: this.store.confirmedAct(account, intentId) } }
    this.store.put(scope, { request_sha256: rsha, state: 'in_flight', status: null, body: null })
    return { do: 'act' }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  finish(account: string, operation: string, key: string, status: number, body: any, o: { intentId?: string; actId?: string } = {}): void {
    const scope = `${account}\u0000${operation}\u0000${key}`
    const code = body.ok ? null : (body.error || {}).code
    if (code === 'outcome_unknown') return
    if (body.ok || STORE_FOR_REPLAY.includes(code)) {
      const row = this.store.get(scope)
      this.store.put(scope, { ...(row || { request_sha256: '', status: null, body: null }), state: 'done', status, body } as Row)
      if (body.ok && o.intentId && o.actId) this.store.confirm(account, o.intentId, o.actId)
    } else this.store.delete(scope)
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  resolve(account: string, operation: string, key: string, status: number, body: any, o: { intentId?: string; actId?: string } = {}): void {
    this.finish(account, operation, key, status, body, o)
  }
}
