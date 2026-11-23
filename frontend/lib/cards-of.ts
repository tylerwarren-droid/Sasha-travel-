// Sasha 402 · EU 294 P1 · THE ONE MAPPING from a reply's card event to the cards S2 draws (/s2 and /next) — moved out of S2App so the
// backend's test runs THIS code on the stream's own events (node strips the types): what the server counts as drawn on S2
// (app/agent/sasha.py S2_NEEDS) is held equal to what this draws. The identity of a card is ev.card_key, never ev.card (a payload).
/* eslint-disable @typescript-eslint/no-explicit-any -- a stream event, shaped by its own `kind` (agent/sasha.py) */
type Ev = Record<string, any>

/** The cards the person sees — as the backend's own shown_cards (agapi/venues.py): the ranking's default order, its `show` count. */
export function shownCards(preset: Ev): Ev[] {
  if (Array.isArray(preset.cards) && preset.cards.length) return preset.cards
  const all = (Array.isArray(preset.all) ? preset.all : []).filter((c: Ev) => c && c.place_id)
  const rk = preset.ranking || {}
  const order: string[] | undefined = (rk.orders || {})[rk.default || 'rated']
  const by = new Map(all.map((c: Ev) => [c.place_id, c]))
  const cards = order ? order.map(i => by.get(i)).filter(Boolean) : all
  return (cards as Ev[]).slice(0, Number(preset.show) || 5)
}

export function cardsOf(ev: Ev): Ev[] {
  const k = String(ev.kind || '')
  if (k === 'venues' && ev.preset) { const cs = shownCards(ev.preset); return cs.length ? [{ k: 'venues', cards: cs }] : [] }
  if (k === 'discover' && Array.isArray(ev.groups) && Array.isArray(ev.options) && ev.options.length)   // Sasha 276 · refused: no cards
    return [{ k: 'discover', groups: ev.groups, options: ev.options, pick: ev.pick || null, sources_url: ev.sources_url || null }]
  if (k === 'read_back' && Array.isArray(ev.read_back)) return [{ k: 'read_back', lines: ev.read_back, what: ev.what, live: ev.live, status: ev.status, total: ev.total_eur, act: ev.act, head: ev.head,
    ...(ev.pay && typeof ev.pay === 'object' ? { pay: ev.pay } : {}),
    ...(Array.isArray(ev.choices) && ev.choices.length && ev.read_back_id ? { ask: String(ev.ask || ''), choices: ev.choices, read_back_id: String(ev.read_back_id) } : {}) }]
  if (k === 'calendar' && ev.links) return [{ k: 'calendar', title: ev.title, links: ev.links, update: ev.update }]   // Sasha 312
  if (k === 'keep_capture') return [{ k: 'keep_capture', what: ev.what === 'loyalty' ? 'loyalty' : 'passport' }]
  if (k === 'wa_open' && typeof ev.open === 'string' && ev.open.startsWith('https://wa.me/')) return [{ k: 'wa_open', to: ev.to || {}, text: String(ev.text || ''), open: ev.open, why: String(ev.why || '') }]   // Sasha 230
  if (k === 'capabilities' && Array.isArray(ev.groups)) return [{ k: 'capabilities', groups: ev.groups }]
  if (k === 'kind_ask' && Array.isArray(ev.choices) && ev.choices.length) return [{ k: 'kind_ask', ask: String(ev.ask || ''), choices: ev.choices.map(String) }]   // Sasha 297
  if (k === 'plans' && Array.isArray(ev.items)) return [{ k: 'plans', items: ev.items, on: ev.on, updates: ev.calendar_updates }]   // Sasha 312
  if (k === 'group_list' && ev.title) return [{ k: 'group_list', title: String(ev.title), rows: Array.isArray(ev.rows) ? ev.rows : [], counts: ev.counts, link: String(ev.link || '/group'), empty: ev.empty ?? null,
    ...(typeof ev.report === 'string' && ev.report.startsWith('https://') ? { report: ev.report } : {}),
    ...(Array.isArray(ev.todos) ? { todos: ev.todos } : {}), ...(typeof ev.check === 'string' ? { check: ev.check } : {}) }]   // Sasha 345 · 385: + the trip's final report · 394: + its to-dos (Pacioli's)
  if (k === 'notice' && ev.title) return [{ k: 'notice', title: String(ev.title), lines: Array.isArray(ev.lines) ? ev.lines : [], status: ev.status }]
  if (k === 'pay_here') return [{ k: 'pay', client_secret: ev.client_secret, url: ev.url, total_eur: ev.total_eur, already_paid: ev.already_paid }]
  if (k === 'pay' && typeof ev.url === 'string' && ev.url.startsWith('https://')) return [{ k: 'paylink', url: ev.url, label: typeof ev.label === 'string' ? ev.label : undefined }]   // Sasha 349
  if (k === 'counter_card' && ev.card) return [{ k: 'counter_card', card: ev.card }]   // CR 75 · fine print
  if (k === 'my_cards') return [{ k: 'my_cards', cards: ev.cards || [] }]
  if (k === 'accident' && ev.view) return [{ k: 'accident', view: ev.view }]
  if (k === 'claim_status' && ev.claim) return [{ k: 'claim_status', claim: ev.claim }]
  if (k === 'operators' && Array.isArray(ev.buttons) && ev.buttons.length)   // Sasha 320 · AgAPI's hand-over, every kind
    return [{ k: 'operators', line: String(ev.line || ''), buttons: ev.buttons.filter((b: { url?: unknown; label?: unknown }) => typeof b?.url === 'string' && String(b.url).startsWith('https://') && typeof b?.label === 'string') }]
  if (k === 'handover' && typeof ev.url === 'string' && (ev.url.startsWith('https://') || (ev.external && ev.url.startsWith('http://'))))   // Sasha 286 · a venue's own site may be http
    return [{ k: 'handover', url: ev.url, external: !!ev.external, label: typeof ev.label === 'string' ? ev.label : undefined,
              alts: Array.isArray(ev.alternatives) ? ev.alternatives.filter((x: { link?: unknown }) => typeof x?.link === 'string' && /^(https:\/\/|tel:)/.test(String(x.link))) : undefined }]   // Sasha 236
  if (k === 'prepared' && typeof ev.url === 'string') return [{ k: 'prepared', ev }]   // Sasha 248
  if (k === 'subscriptions' && Array.isArray(ev.items)) return [{ k: 'subscriptions', items: ev.items, total: ev.total, source: ev.source }]   // CR 84
  if (k === 'activities' && Array.isArray(ev.cards)) return [{ k: 'activities', cards: ev.cards, unread: Array.isArray(ev.unread) ? ev.unread : [], date: ev.date }]   // CR 81
  // Sasha 349 · a search's OPTIONS, in the conversation (the 236 trip-board card stood in for them: no cards, and a placeholder trip)
  const opts = (c: Ev | undefined, kind: 'flight' | 'hotel'): Ev[] => (c && Array.isArray(c.options) && c.options.length
    ? [{ k: 'options', kind, title: String(c.title || ''), leg: c.leg, options: c.options }] : [])
  if (k === 'flights') return opts(ev.card, 'flight')
  if (k === 'stays') return opts(ev.card, 'hotel')
  if (k === 'trip' && !(Array.isArray(ev.cards) && ev.cards.length) && !ev.total) return [{ k: 'trip' }]   // Sasha 354 · what is pending now: the trip's ONE card (its next actions: Pay · Keep it / Switch)
  if (k === 'trip') return [...(Array.isArray(ev.cards) ? ev.cards.flatMap((c: Ev) => opts(c, 'flight')) : []), ...(ev.total ? [{ k: 'total', total: ev.total }] : [])]
  if (k === 'total' && ev.total) return [{ k: 'total', total: ev.total }]
  if (k === 'flight_chosen') return [...(ev.total ? [{ k: 'total', total: ev.total }] : []), { k: 'trip' }]   // the trip exists now: its card
  return []
}
