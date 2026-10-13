// Sasha 259 · THE PHONE GATE (Tyler, row 884): /s2 at 390×844 — every visible control and line of text measured; ANY overlap fails
// (exit 1). Usage: node scripts/phone-overlap.mjs <url> <cookie-header-value?> [screenshot.png]
// Needs Playwright (the runner's / the scoreboard's): PLAYWRIGHT_MODULE=<path to playwright> if it isn't installed here.
import { overlaps } from '../lib/overlap.mjs'
const [url, cookie, shot] = process.argv.slice(2)
const pw = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const { chromium } = pw.default || pw
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined })
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true })
if (cookie) { const [name, ...v] = cookie.split('='); await ctx.addCookies([{ name, value: v.join('='), url }]) }
const page = await ctx.newPage()
await page.goto(url, { waitUntil: 'load', timeout: 60000 })
await page.waitForTimeout(Number(process.env.SETTLE_MS || 14000))
const boxes = await page.evaluate(() => {
  const vis = (e) => { const s = getComputedStyle(e); const r = e.getBoundingClientRect(); return s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05 && r.width > 2 && r.height > 2 && r.bottom > 0 && r.top < innerHeight }
  const name = (e) => (e.getAttribute('aria-label') || e.textContent || e.tagName).trim().slice(0, 40)
  // the controls, and the leaf text under the composer row (what Tyler saw piled up): never containers
  const els = [...document.querySelectorAll('button, input, a, footer p, [role="button"]')].filter(vis)
  return els.map((e) => { const r = e.getBoundingClientRect(); return { name: name(e), x: r.x, y: r.y, w: r.width, h: r.height } })
})
if (shot) await page.screenshot({ path: shot })
await browser.close()
const bad = overlaps(boxes)
console.log(JSON.stringify({ boxes: boxes.length, overlaps: bad }))
process.exit(bad.length ? 1 : 0)
