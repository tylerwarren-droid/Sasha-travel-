import type { Tab } from './types'

// kanoe-site-scope.md §11 (EU 136), verbatim. CONCEPT only: no drawing of any government site.
export const spain: Tab = {
  route: '/spain-services',
  title: 'Spain public services — Kanoe',
  description: 'The new-resident wall, prepared for you: you press the button.',
  headline: 'The new-resident wall, prepared for you: you press the button.',
  lines: [
    { status: 'proven', evidence: 'the study of health appointments in Madrid, Catalonia and Andalusia (kanoe-site-scope.md §6)',
      text: 'We\'ve studied how health appointments work in Madrid, Catalonia and Andalusia, and what an assistant may lawfully do there.' },
    { status: 'concept', evidence: 'designed, not built',
      text: 'Sasha would prepare everything — the identifiers, the order, the official page — and remind you; you sign in and press, every time.' },
    { status: 'concept', evidence: 'not yet studied',
      text: 'The padrón and utilities are next to study.' },
  ],
  statusLine: 'A concept. Nothing here is built, and nothing will be until a data-protection assessment is done.',
  demo: { kind: 'concept', sentence: 'Concept: designed, not built.' },
}
