import type { Tab } from './types'

// kanoe-site-scope.md §11 (EU 136), verbatim. The live flow is CR 1's (the CR tab's code; this page only links to it).
export const campusme: Tab = {
  route: '/campusme',
  title: 'CampusMe — Kanoe',
  description: 'Campus visits, booked the way universities want them.',
  headline: 'Campus visits, booked the way universities want them.',
  lines: [
    { status: 'proven', evidence: 'CR 1 (M1): backend/products/campus — each university\'s own visit calendar, read live',
      text: 'CampusMe reads each university\'s own visit calendar, live, and shows real sessions with real spaces, or says plainly when a month isn\'t published yet.' },
    { status: 'proven', evidence: 'CR 1 (M1): the hand-over page /campus-handover/[id] — the form filled, stopped before Register',
      text: 'One yes fills the school\'s own form from the family\'s saved details, and stops before Register: a person presses.' },
    { status: 'proven', evidence: 'CR 1 (M1): Yale and Penn proven; P807on: 8 of the 10 universities on the same calendar system',
      text: 'Proven on Yale and Penn; 8 of the 10 universities we studied run the same calendar system.' },
  ],
  statusLine: 'Working on WhatsApp in our sandbox, read-only on the universities\' sites. Nothing has been submitted to a university.',
  demo: { kind: 'live', sentence: 'Live: real calendars, real sessions. We stop before the school\'s Register button.',
    // the CR tab's dedicated SHOWCASE page (stable to 31 Dec 2026; the student is fictional; noindex)
    links: [{ href: '/campus-handover/vuvpvu6fG71M5b_rxtEsag', label: 'See a hand-over: Yale\'s real session and form, read live on 3 Oct 2026 — the student is fictional →' }],
    note: 'Shown live on WhatsApp in the investor demo (sandbox). Not open to the public yet.' },
}
