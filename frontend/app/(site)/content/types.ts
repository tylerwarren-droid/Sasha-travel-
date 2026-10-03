/**
 * Sasha 123 · the new site's tab content is DATA (kanoe-site-scope.md §9.3): a claim can't be typed without its status,
 * and a demo can't be typed without its label.
 *   ✅ proven — in code, a live row or a saved source · ◐ founder-reported · ○ concept: designed, not built.
 *   LIVE — the real product · CLICK-THROUGH — a scripted walk ("Illustration") · CONCEPT — a static explanation.
 */
export type Status = 'proven' | 'reported' | 'concept'
export type DemoKind = 'live' | 'click-through' | 'concept'
export type Line = { text: string; status: Status; evidence: string }
export type DemoLink = { href: string; label: string; external?: boolean }
export type Tab = {
  route: string
  title: string                 // <title> and the menu's meaning
  description: string           // the page's meta description
  headline: string
  lines: [Line, Line, Line]     // §11: three lines, each with its mark
  statusLine: string            // §11: always shown, styled as status
  demo: { kind: DemoKind; sentence: string; links?: DemoLink[]; austen?: boolean; note?: string }
}
