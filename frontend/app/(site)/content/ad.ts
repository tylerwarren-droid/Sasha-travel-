import type { Tab } from './types'

// kanoe-site-scope.md §11 (EU 136), verbatim. Figures dated "as of 2 Oct 2026" (§9.4): never live counts.
export const ad: Tab = {
  route: '/applied-diligence',
  title: 'Applied Diligence — Kanoe',
  description: 'Due diligence you can defend.',
  headline: 'Due diligence you can defend.',
  lines: [
    { status: 'proven', evidence: 'Applied Diligence: lib/jurisdiction-agents (OFAC, OFSI, UN screens; the instant registers), as of 2 Oct 2026',
      text: 'Every case is screened free against the US (OFAC), UK (OFSI) and UN sanctions lists; company registers in 12 EU countries and 3 US states answer in seconds (as of 2 Oct 2026).' },
    { status: 'proven', evidence: 'Applied Diligence: the veracity scoring (each score labelled an AI estimate)',
      text: 'Question the subject, and their answers are checked against the evidence on the case. Every score is an AI estimate, and labelled so.' },
    { status: 'proven', evidence: 'Applied Diligence: the case report (one dated PDF, every finding with its source and date)',
      text: 'The verdict shows what it rests on, and every finding names its source and its date, in one dated PDF.' },
  ],
  statusLine: 'Live at applieddiligence.com, in beta. No paying customers yet.',
  demo: { kind: 'live', sentence: 'Live: the real product, at applieddiligence.com.',
    links: [{ href: 'https://applieddiligence.com', label: 'applieddiligence.com →', external: true }] },
}
