/**
 * Sasha 142 · THE HUB at project.kanoe.ai/agapi: AgAPI on top, then one tab per product. Copy: EU 152,
 * docs/business/agapi-hub-pitches.md (4 Oct 2026). Sources: EU's market research of the same day; every URL below is
 * the one it gives.
 *
 * Rules, held by the types and by scripts/agapi-hub.test.mjs:
 *  · every claim carries a mark (✅ built · 🧪 TEST bookings or a fictional subject · ○ concept · ◐ founder-reported);
 *  · every figure carries at least one figure mark ([S] sourced · [V] vendor · [E] our estimate · [F] founder
 *    assumption) and every [S]/[V] figure at least one source URL, read at source (●) or seen in a search summary (○);
 *  · a vendor range is quoted as a range, never a midpoint; a SOM is its variables, never a number;
 *  · a tab whose copy isn't in is `ready: false` and is NOT shown — no placeholder is ever published.
 */

export type Claim = 'built' | 'test' | 'concept' | 'reported'
export type FigMark = 'S' | 'V' | 'E' | 'F'
export type Source = { url: string; read: boolean }   // read: ● fetched at source; false: ○ a search summary only

export type Line = { mark: Claim; text: string }
export type Figure = { row: string; figure: string; method: string; marks: [FigMark, ...FigMark[]]; note?: string; sources: Source[] }
export type Pitch = {
  key: string
  name: string
  badge?: string
  ready: boolean
  problem: string
  does: Line[]
  agents: { agent: 'Magellan' | 'Sherlock' | 'Austen' | 'Pacioli'; text: string; mark: Claim }[]
  market: Figure[]
  model: Line[]
  status: Line[]
  demo: { href?: string; label?: string; whatsapp: string }
  /** Sasha 155 · "Try it now": the product itself, its chat already in its own mode */
  tryHref?: string
}

export const CLAIM_GLYPH: Record<Claim, string> = { built: '✅', test: '🧪', concept: '○', reported: '◐' }
export const CLAIM_WORD: Record<Claim, string> = {
  built: 'Built or live', test: 'Works, with TEST bookings or a fictional subject', concept: 'Concept: designed, not built',
  reported: 'Founder-reported',
}
export const FIG_WORD: Record<FigMark, string> = {
  S: 'sourced: an official statistic', V: 'a vendor estimate (a market-research firm)', E: 'our estimate, the method shown',
  F: 'a founder assumption, left as a variable',
}

const S = (url: string, read = false): Source => ({ url, read })

export const HUB = {
  headline: 'One method, proven in five products. The shared engine is what this round funds.',
  agents: [
    { name: 'Magellan', role: 'finds', text: 'Where a thing can be done, and how: the venue’s own form, the school’s own calendar, the register, the consulate’s own page. Robots and terms first.' },
    { name: 'Sherlock', role: 'obtains, lawfully', text: 'The record, the answer or the document, by a route a person has approved.' },
    { name: 'Austen', role: 'completes, after your yes', text: 'The booking, the form, the request. One yes, bound to the exact words. It never signs or declares for you.' },
    { name: 'Pacioli', role: 'reconciles', text: 'What each source says, side by side, and where they disagree. A record of the check, never a verdict.' },
  ],
  status: [
    { mark: 'built', text: 'The method works in five products today, in two codebases (Sasha’s and Applied Diligence’s).' },
    { mark: 'concept', text: 'The shared engine is the plan: Pacioli first, then Magellan, then Austen, each tested offline against today’s answers before anything switches.' },
  ] as Line[],
  whatsapp: 'Try it on WhatsApp: type relocate, campus, españa or diligence.',
  marketKey: 'TAM is the spend or volume the product touches; SAM the part we can reach with what’s built and the routes we may use; SOM what we’d take in three years, a founder assumption left as a variable. Sizes are spend or volume, not our revenue.',
}

export const PITCHES: Pitch[] = [
  {
    key: 'sasha', name: 'Sasha (Vietnam)', ready: true, tryHref: '/',
    problem: 'A visitor in Hanoi or Hoi An wants the good local place, not the one with an English booking widget. Those places take bookings by their own form, email or phone, in Vietnamese, in their own hours.',
    does: [
      { mark: 'built', text: 'Ask once, on WhatsApp or the web. Sasha finds the venues and shows cards, with photos where the venue publishes one (about 1 in 3 in Vietnam).' },
      { mark: 'built', text: 'After one yes, she books by the venue’s own form or email. Calls to Vietnam are in English; +84 calls aren’t connected yet.' },
      { mark: 'test', text: 'Hotels: “Reserve (TEST)”, or a real room request to the hotel (✅). Flights: TEST bookings.' },
      // CR 50 · each line confirmed true and live by the Sasha tab (7 Oct): no real Apple Pay tap has completed a whole trip yet
      { mark: 'test', text: 'Laptop books, phone pays: a whole Vietnam trip priced and read back on the laptop; one Apple Pay tap is sent to the phone (TEST).' },
      { mark: 'test', text: 'A tattoo-studio request: found, sent by email (our test venue stands in), and filed under Requests.' },
      { mark: 'built', text: 'Every journey in one place: Sasha’s trips space, with a tab per journey.' },
    ],
    agents: [
      { agent: 'Magellan', mark: 'built', text: 'Reads each venue’s own site for its routes; Vietnam is one of the countries it reads.' },
      { agent: 'Sherlock', mark: 'built', text: 'Obtains the venue’s answer in writing: an email to Sasha’s own address, matched to the booking.' },
      { agent: 'Austen', mark: 'built', text: 'Books by form, then one tap, then email, then a call, on one yes covering the plan.' },
      { agent: 'Pacioli', mark: 'built', text: 'Checks the venue’s words against the request: “booked” only on their words; “unclear” is never shown as booked.' },
    ],
    market: [
      { row: 'TAM (spend)', figure: '≈ US$3.4bn a year on food and drink by international visitors to Vietnam',
        method: '21.17m arrivals (2025) × US$726.7 average spend per visitor (2023) × 21.9% on food and drink (2019 survey)',
        marks: ['E', 'S'], note: 'Inputs from different years: low confidence.',
        sources: [S('https://en.vietnamplus.vn/international-arrivals-to-vietnam-hit-new-record-in-2025-up-over-20-post335449.vnp'),
                  S('https://vneconomy.vn/khach-quoc-te-den-viet-nam-ket-qua-nam-2023-ky-vong-nam-2024.htm')] },
      { row: 'Context', figure: 'Tours, activities and attractions: US$271bn worldwide (2025) → US$342bn (2029)', method: 'Arival + Phocuswright',
        marks: ['V'], sources: [S('https://arival.travel/article/experiences-surging-towards-342-billion/', true)] },
      { row: 'SAM (visits)', figure: 'Up to ≈ 12m international visits a year to Hanoi + Hoi An',
        method: 'Hanoi 7.82m (2025) + Hoi An ≈ 4.5m (2024). Visits overlap between cities, so this is an upper bound',
        marks: ['S', 'E'], sources: [S('https://en.vietnamplus.vn/hanoi-welcomes-more-than-337-million-visitors-in-2025-post334955.vnp'),
                                    S('https://bvhttdl.gov.vn/khach-quoc-te-den-hoi-an-tang-manh-20240115160302465.htm')] },
      { row: 'Growth', figure: '17.7m arrivals Jan–Sep 2026, +14.5% y/y; the 2026 target is 25m', method: 'National Statistics Office via Vietnam News',
        marks: ['S'], sources: [S('https://vietnamnews.vn/society/1801167/viet-nam-welcomes-17-7-million-foreign-visitors-in-nine-months-71-per-cent-yearly-target-met.html', true)] },
      { row: 'SOM', figure: '[confirmed bookings per year in year 3] × [fee per confirmed booking]',
        method: 'No figure until the pilot measures the confirmation rate', marks: ['F'], sources: [] },
    ],
    model: [{ mark: 'concept', text: 'B2B2C first: hotels and concierge operators pay a fee per confirmed booking, plus a per-property fee (prices: founder assumptions). Consumer tiers later. No revenue today.' }],
    status: [
      { mark: 'built', text: 'Vietnam: discovery, and booking by form or email; calls in English, with +84 not connected yet.' },
      { mark: 'built', text: 'Madrid: the full ladder, in closed beta. WhatsApp on our own number. The confirmation rate isn’t published yet.' },
    ],
    demo: { href: '/', label: 'project.kanoe.ai, the Sasha Vietnam site', whatsapp: 'Just ask, e.g. “dinner for 2 in Hoi An tomorrow at 7pm”' },
  },
  {
    key: 'applied-diligence', name: 'Applied Diligence', ready: true, tryHref: 'https://applieddiligence.com',
    problem: 'A decision about a company or a person (to onboard, invest, award a contract) has to be defensible: evidence from the official source, dated, with every gap said out loud. Analysts assemble it by hand, one register at a time.',
    does: [
      { mark: 'built', text: 'Free sanctions screening (US OFAC, UK OFSI, UN) on every case.' },
      { mark: 'built', text: 'Company registers on sale in the 27 EU countries and the UK.' },
      { mark: 'built', text: 'The subject’s answers are checked against the evidence, labelled as AI estimates; a verdict that shows its working, and one dated packet.' },
    ],
    agents: [
      { agent: 'Magellan', mark: 'reported', text: 'Discovers registers and forms; an admin accepts each.' },
      { agent: 'Sherlock', mark: 'built', text: 'Obtains the official record: 15 certified instant routes (◐ an attended route for hard registers such as Greece).' },
      { agent: 'Austen', mark: 'built', text: 'Completes approved acts, with six recorded outcomes.' },
      { agent: 'Pacioli', mark: 'built', text: 'Checks a case’s completeness (one route); reconciliation isn’t wired yet (○).' },
    ],
    market: [
      { row: 'TAM (software spend)', figure: 'US$6.1–11.1bn third-party-risk software (2025); background-check software US$4.8–5.1bn (2025)',
        method: 'Nine vendor estimates for third-party risk, which disagree by about 2×. “Due diligence software” isn’t a category of its own',
        marks: ['V'], note: 'A wide range: quoted as a range, never a midpoint.',
        sources: [S('https://www.researchandmarkets.com/reports/5785704/third-party-risk-management-market-report'),
                  S('https://www.futuremarketinsights.com/reports/third-party-risk-management-market'),
                  S('https://www.theinsightpartners.com/reports/third-party-risk-management-market'),
                  S('https://www.fortunebusinessinsights.com/background-check-software-market-111189')] },
      { row: 'Context (EU)', figure: '33m+ active enterprises (2023)', method: 'Eurostat',
        marks: ['S'], sources: [S('https://ec.europa.eu/eurostat/web/products-eurostat-news/w/ddn-20251013-1', true)] },
      { row: 'SAM (Spain, procurement)', figure: '220,291 contracts awarded in 2023 (€78.2bn), 2.99 bidders per lot: ≈ 659k bids a year, of which 220k winners must be fully verified (LCSP art. 150.2)',
        method: 'OIReScon annual supervision report 2024 × the bidder average', marks: ['S', 'E'],
        sources: [S('https://www.hacienda.gob.es/RSC/OIReScon/informe-anual-supervision-2024/ias2024-modulo1.pdf', true)] },
      { row: 'SAM (Spain, AML)', figure: '26,044 obliged entities (1,085 financial + 24,959 non-financial, end-2022)', method: 'SEPBLAC',
        marks: ['S'], sources: [S('https://www.sepblac.es/wp-content/uploads/2024/03/Memoria-informacion-estadistica-2018-2022.pdf')] },
      { row: 'SOM', figure: '[share of Spanish awardee checks] × [price per file]', method: 'e.g. 1% of 220k = 2,200 files a year × [price]',
        marks: ['F'], sources: [] },
    ],
    model: [
      { mark: 'built', text: 'Per check, in credits, live: 3 credits ≈ US$2.99 per automated register check; 25+ credits for a person’s check. No purchases yet (2 organisations, 0 purchases, 2 Oct 2026).' },
      { mark: 'concept', text: 'Next: a Registry API, and procurement integrity for public buyers.' },
    ],
    status: [{ mark: 'built', text: 'Live at applieddiligence.com, in beta.' }],
    demo: { href: 'https://applieddiligence.com', label: 'applieddiligence.com',
            whatsapp: 'Type diligence, then “check SIREN 542051180 in France”: the register’s own result, source and date, marked PREVIEW. The Netherlands is never queried (KVK’s terms).' },
  },
  {
    key: 'campusme', name: 'CampusMe', ready: true, tryHref: '/preview/campusme',
    problem: 'A family visiting universities juggles a dozen calendars, registration forms and the travel between campuses.',
    does: [
      { mark: 'built', text: 'Reads each university’s own visit calendar, live (Yale and Penn proven).' },
      { mark: 'built', text: 'Prepares the school’s own registration from the family’s saved details, and stops before Register: a person presses.' },
      { mark: 'test', text: 'Plans the trip around the visits: flights and hotels as TEST bookings, and the drive between campuses checked by Google (✅). Train times aren’t checked.' },
    ],
    agents: [
      { agent: 'Magellan', mark: 'built', text: 'Each school’s visit calendar, robots first.' },
      { agent: 'Sherlock', mark: 'built', text: 'The sessions and spaces, read-only, from the school’s own domain.' },
      { agent: 'Austen', mark: 'built', text: 'The hand-over, prepared, never submitted.' },
      { agent: 'Pacioli', mark: 'built', text: '“Registered” only when the confirmation names the day.' },
    ],
    market: [
      { row: 'TAM (families)', figure: '≈ 1.36m US first-year applicants who visit a campus',
        method: '1,527,328 Common App applicants (2025–26) × 89% who visited a campus (a vendor survey whose wording conflicts on “before applying” vs “before enrolling”)',
        marks: ['S', 'V', 'E'], note: 'Medium-low confidence.',
        sources: [S('https://www.commonapp.org/reports/end-season-report-2025-2026-first-year-application-trends/'),
                  S('https://www.niche.com/about/wp-content/uploads/2024/09/2024-Niche-Enrollment-Survey.pdf')] },
      { row: 'TAM (spend)', figure: '≈ US$1.4–4.1bn of visit travel', method: '1.36m × US$1,000–3,000 per family across a search (consumer-finance articles, not survey-grade)',
        marks: ['E'], note: 'Low confidence.', sources: [S('https://collegehound.com/blog/how-to-save-money-on-the-college-application-process/')] },
      { row: 'Plus', figure: '1.18m international students in the US; 277k new (2024/25)', method: 'IIE Open Doors 2025',
        marks: ['S'], sources: [S('https://opendoorsdata.org/wp-content/uploads/2025/11/OD25_Fast-Facts.pdf', true)] },
      { row: 'SAM', figure: '≈ 320k students who visit more than 5 campuses', method: '1.53m × 21% (the same vendor survey)',
        marks: ['E'], sources: [S('https://www.niche.com/about/wp-content/uploads/2024/09/2024-Niche-Enrollment-Survey.pdf')] },
      { row: 'SOM', figure: '[families per year] × [price per trip or plan]', method: '—', marks: ['F'], sources: [] },
    ],
    model: [{ mark: 'concept', text: 'Per trip, or per family per season (price: a founder assumption). B2B to college counsellors and international-student agencies. No revenue.' }],
    status: [{ mark: 'built', text: 'Working on WhatsApp in our test setup, read-only on the universities’ sites. Nothing is ever submitted.' }],
    demo: { href: '/preview/campusme', label: 'the CampusMe preview', whatsapp: 'Type campus, then “campus visits at Yale and Penn in November for my son”' },
  },
  {
    key: 'relocateme', name: 'RelocateMe', ready: true, tryHref: '/preview/relocateme',
    problem: 'A first Spanish residence application comes back for one fact that disagrees across documents. Then there’s the trip, the first nights, and a dozen deadlines.',
    does: [
      { mark: 'built', text: 'The passport photo is read and checked against its own check digits.' },
      { mark: 'built', text: 'The official EX-01 is prepared from the person’s own words and checked field by field. We never sign it and never file it. The consulate’s own route and list (London and 7 US consulates).' },
      { mark: 'test', text: 'Then flights and the first nights as TEST bookings, and one itinerary with every deadline (✅).' },
    ],
    agents: [
      { agent: 'Magellan', mark: 'built', text: 'The consulate’s own appointment page and checklist.' },
      { agent: 'Sherlock', mark: 'built', text: 'The passport’s values from a photo, each confirmed.' },
      { agent: 'Austen', mark: 'built', text: 'The EX-01 fill, refused on any signature, consent or intent box.' },
      { agent: 'Pacioli', mark: 'built', text: 'The checker: cross-fact agreement and staleness.' },
    ],
    market: [
      { row: 'TAM (residence documents)', figure: '1,577,842 residence documents granted in Spain in 2025',
        method: 'OPI (Ministerio de Inclusión). All routes, renewals included, so an upper bound on new files', marks: ['S'],
        sources: [S('https://www.inclusion.gob.es/en/w/crece-un-7-8-el-numero-de-documentos-de-residencia-concedidos-en-2025-por-el-aumento-de-peticionarios-de-venezuela-ucrania-y-reino-unido')] },
      { row: 'SAM (stock)', figure: '84,957 people holding non-lucrative residence', method: 'OPI; a stock, not an annual flow (the flow wasn’t found)',
        marks: ['S'], sources: [S('https://www.inclusion.gob.es/en/w/crece-un-7-8-el-numero-de-documentos-de-residencia-concedidos-en-2025-por-el-aumento-de-peticionarios-de-venezuela-ucrania-y-reino-unido')] },
      { row: 'SAM (who)', figure: '382,474 UK nationals with residence documents (end-2025); ~49–51k US nationals resident (2024–25)',
        method: 'OPI and INE, via secondary sites', marks: ['S'],
        sources: [S('https://www.inclusion.gob.es/documents/d/opi/indicadores_ReinoUnido'), S('https://spainguru.es/2026/06/07/americans-living-in-spain/')] },
      { row: 'Price anchor', figure: 'A lawyer’s fee for a non-lucrative or digital-nomad visa package: €1,500–5,000', method: 'Adviser sites; unconfirmed',
        marks: ['V'], sources: [S('https://www.costaluzlawyers.com/immigration-lawyer-spain-cost/'), S('https://vamospanish.com/spain-legal-services/immigration-lawyer-spain/')] },
      { row: 'SOM', figure: '[files per year] × [price per file]', method: '—', marks: ['F'], sources: [] },
      // Sasha 159 · moved here from EspañaMe (EU 160 §4 row 8): newcomers are RelocateMe's
      { row: 'TAM (people)', figure: '7,437,543 foreign nationals resident in Spain (1 Jul 2026, provisional); 10.29m foreign-born',
        method: 'INE', marks: ['S'], sources: [S('https://www.ine.es/dyngs/Prensa/ECP2T26.htm', true)] },
      { row: 'Flow', figure: '1.58m residence documents granted in 2025 (all routes); the 2026 regularisation drew 1,174,978 applications',
        method: 'OPI; Ministerio de Inclusión', marks: ['S'],
        sources: [S('https://www.inclusion.gob.es/en/w/crece-un-7-8-el-numero-de-documentos-de-residencia-concedidos-en-2025-por-el-aumento-de-peticionarios-de-venezuela-ucrania-y-reino-unido'),
                  S('https://www.inclusion.gob.es/en/w/el-plazo-de-presentacion-de-solicitud-para-la-regularizacion-extraordinaria-concluye-con-1.174.978-solicitudes-recibidas')] },
      { row: 'Demand signal', figure: 'Too few extranjería appointments, flagged by the Defensor del Pueblo (2025 report); no number found',
        method: 'Qualitative', marks: ['S'], sources: [S('https://www.defensordelpueblo.es/noticias/informe-2025-pleno-senado/')] },
    ],
    model: [{ mark: 'concept', text: 'Per file (price: a founder assumption), positioned below a lawyer’s package. B2B to relocation firms, employers and lawyers. No revenue.' }],
    status: [{ mark: 'built', text: 'Working on WhatsApp in our test setup, for a first application from the UK or the US. Renewals and family applications aren’t built. Flights and hotels are TEST.' }],
    demo: { href: '/preview/relocateme', label: 'the RelocateMe preview', whatsapp: 'Type relocate, then “I’m moving to Madrid from London in March”' },
  },
  {
    key: 'espaname', name: 'EspañaMe', badge: 'CONCEPT', ready: true, tryHref: '/preview/espaname',
    problem: 'Every citizen deals with a dozen public offices — each with its own appointment system, ID and deadline — and the people who struggle most are the ones public services most need to reach.',
    does: [
      { mark: 'built', text: 'Health works today in our test setup: a private clinic booked by phone, and public appointments (SERMAS) prepared for you to press.' },
      { mark: 'concept', text: 'DNI renewal, IMV and bono social, padrón change of address, IBI, DGT: read at source on 5 Oct 2026, not built.' },
      { mark: 'built', text: '🇪🇸 Health card on the platform: ID read → official form filled → your centre → cita or walk in.' },   // CR 50
      { mark: 'built', text: 'The rule: Sasha prepares, you press. She never signs in to, books, or calls a public service for you.' },
    ],
    agents: [
      { agent: 'Magellan', mark: 'built', text: 'The official pages.' },
      { agent: 'Sherlock', mark: 'built', text: 'Only what the appointment needs, never why; no stored health identifiers before a data-protection assessment.' },
      { agent: 'Austen', mark: 'built', text: 'The private clinic’s call, after the yes; the SERMAS hand-over, which you press.' },
      { agent: 'Pacioli', mark: 'concept', text: 'Not yet: there’s nothing to reconcile in the concept parts.' },
    ],
    market: [
      // Sasha 159 · EU 160 §4 row 8: EspañaMe's market is the PUBLIC BUYER; the foreign-national rows moved to RelocateMe
      { row: 'Buyer (region)', figure: 'Comunidad de Madrid: an AI virtual assistant for municipal information in 33 municipalities — awarded 27 Aug 2025 for €194,825.84 (base €425,283.20, 22 bids)',
        method: 'Read at source by EU 160, 5 Oct 2026 (contratos-publicos.comunidad.madrid)', marks: ['S'], sources: [] },
      { row: 'Buyer (diputación)', figure: 'Ciudad Real: €3,210,830.28 for 156 digital-inclusion technicians for 12 months (approved 2 Jun 2026)',
        method: 'Read at source by EU 160, 5 Oct 2026 (fempclm.es, the call PDF)', marks: ['S'], sources: [] },
      { row: 'People', figure: '[all residents who use public services]', method: 'To compute from INE', marks: ['E'], sources: [] },
    ],
    model: [{ mark: 'concept', text: 'Public buyers: diputaciones, ayuntamientos and social services, starting with a pilot under the contrato-menor threshold (LCSP art. 118). “Every citizen arrives at your counter with the right papers — or doesn’t need to come. We never bypass your systems.” No revenue.' }],
    status: [{ mark: 'built', text: 'A CONCEPT, with health working in our test setup. No health data is stored until a data-protection assessment is done.' }],
    demo: { href: '/preview/espaname', label: 'the EspañaMe preview', whatsapp: 'Type españa, then “I need a doctor this week”' },
  },
]
