import type { Tab } from './types'

// kanoe-site-scope.md §11 (EU 136), verbatim. The demo: §9.4 — Austen's two saved acts, rendered from their records.
export const agapi: Tab = {
  route: '/',
  title: 'AgAPI — Kanoe',
  description: 'Agents that do the paperwork of the world, lawfully, and prove every step.',
  headline: 'Agents that do the paperwork of the world, lawfully, and prove every step.',
  lines: [
    { status: 'concept', evidence: 'kanoe-site-scope.md §1: the four agents as one method — partly built (see the status line)',
      text: 'Four agents: Magellan finds the source, Sherlock obtains the record by a route a person approved, Austen completes the act after a yes, Pacioli checks the result.' },
    { status: 'proven', evidence: 'Applied Diligence: lib/agapi (the act records); Sasha: booking_signer (the yes, the read-back, the outcome)',
      text: 'Every act needs a person\'s yes, every outcome is recorded as it happened (including "unreachable"), and nothing reads as done unless the source says so.' },
    { status: 'proven', evidence: 'two codebases: Applied Diligence (Next.js) and Sasha (booking_signer, products/campus, products/relocation)',
      text: 'The method runs in two codebases today: Applied Diligence, and Sasha\'s (bookings, CampusMe, relocation).' },
  ],
  statusLine: 'Austen and Pacioli are built; Magellan and Sherlock are partly built. One shared engine across every product is the roadmap, not today.',
  demo: { kind: 'live', austen: true,
    sentence: 'Live: two real acts our agent completed on 23 Sept 2026 — a German register search (no match found) and a Lisbon table it could not reach — shown exactly as recorded.' },
}
