import type { Tab } from './types'

// kanoe-site-scope.md §11 (EU 136), verbatim. ⛔ Never print a count split of the form's fields (§11): the screen derives its own. The live flow is CR 1's (the CR tab's code; this page only links to it).
export const relocation: Tab = {
  route: '/relocation',
  title: 'Relocation — Kanoe',
  description: 'Moving to Spain: your file prepared, checked, and handed to you to sign.',
  headline: 'Moving to Spain: your file prepared, checked, and handed to you to sign.',
  lines: [
    { status: 'proven', evidence: 'CR 1 (M2–M3): backend/products/relocation — WhatsApp answers, the passport photo read against its check digits',
      text: 'Answer on WhatsApp, or send a photo of your passport (checked against its own check digits). Every value is read back for your yes.' },
    { status: 'proven', evidence: 'CR 1 (M2): the official EX-01, each box with its provenance; the checker agent',
      text: 'The official EX-01 form, filled from your own words, each box naming where its value came from, and a checker that flags what doesn\'t agree.' },
    { status: 'proven', evidence: 'CR 1 (M2–M3): "LEFT FOR THE APPLICANT — NOT SIGNED"; the consulate\'s own route and checklist, dated',
      text: 'We never sign, never tick a consent, and never file. We give you the consulate\'s own appointment page and its own checklist, with its date.' },
  ],
  statusLine: 'Working on WhatsApp in our sandbox, for a first application lodged from the UK. Other consulates and family or representative sections aren\'t built yet.',
  demo: { kind: 'live', sentence: 'Live: the real flow. The applicant shown here is fictional.',
    // the CR tab's dedicated SHOWCASE page (stable to 31 Dec 2026; the applicant is fictional; noindex)
    links: [{ href: '/relocation-file/KZjdXS_8HLk5I9nW76SW_A', label: 'See a prepared EX-01 (fictional applicant) →' }],
    note: 'Shown live on WhatsApp in the investor demo (sandbox). Not open to the public yet.' },
}
