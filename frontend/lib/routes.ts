/**
 * Sasha 368 · ONE ROUTE MAP — what every URL on project.kanoe.ai serves. "/" was moved twice by a page edit (Sasha 123: the six-tab
 * site; Sasha 142: the Sasha Vietnam page) with nothing to say who owns it (Tyler, 11 Nov 06:44). This map is the owner; a test
 * (backend/tests/test_s368_one_route_map.py) fails if "/" stops serving the portal or if any page, middleware, redirect or rewrite
 * claims "/". Change a URL's owner HERE, and its page with it.
 */
export const ROUTES = {
  '/': 'the Kanoe portal — Teaser · Investor Deck · Onboarding · TDM · Data Strategy · Demo (app/page.tsx; restored from git, Sasha 368)',
  '/deck': 'the portal: Investor Deck',
  '/walkthrough': 'the portal: Onboarding',
  '/tdm': 'the portal: TDM',
  '/data-strategy': 'the portal: Data Strategy',
  '/demo': 'the portal: Demo — today\'s Sasha (SASHA), framed',
  '/archive': 'a redirect to "/" (next.config.ts) — the portal lived here 3 Oct – 11 Nov',
  '/s2': 'Sasha — today\'s (the latest)',
  '/next': 'Sasha S1',
  '/group': 'the Group page',
  '/vietnam': 'the Sasha Vietnam site (Stripe returns there)',
  '/agapi': 'the AgAPI hub (the five product tabs)',
} as const

/** Every Sasha link or tab on the portal opens today's Sasha — never an older page. */
export const SASHA = '/s2'
