// CR 22 · LIVE HAND-OVER PROTOTYPE — OUR test venue ONLY. A browser fills the venue's own form from Sasha's draft up to
// the human step, then STOPS: nothing is submitted. What a cloud browser would hand the guest is this same session; here
// we measure what's left for the guest and whether any challenge appears. Never pointed at a platform or a real venue.
//   node handover-proto.mjs   (needs playwright-core and a local Chromium)
import { chromium, devices } from 'playwright-core'
const TEST_VENUE = 'https://sasha-travel-production.up.railway.app/api/booking/test-venue/plain'   // ours — and only ours
const draft = { fecha: '2027-03-01', hora: '11:00', personas: '1', nombre: 'Ana Ejemplo (fictional)', email: 'ana.ejemplo@example.com',
                telefono: '+34600000000', comentarios: 'Kanoe CR 22 prototype — not a booking' }
const exe = process.env.HOME + '/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
const b = await chromium.launch({ executablePath: exe })
const p = await (await b.newContext(devices['iPhone 13'])).newPage()
const t0 = Date.now()
const resp = await p.goto(TEST_VENUE, { waitUntil: 'networkidle' })
const loaded = Date.now() - t0
const fields = await p.$$eval('form input, form select, form textarea', els => els.map(e => ({
  name: e.name, type: e.type || e.tagName.toLowerCase(), required: e.required, hidden: e.type === 'hidden' || e.style.display === 'none' })))
let filled = 0
for (const [k, v] of Object.entries(draft)) { const el = await p.$(`[name="${k}"]`); if (el) { await el.fill(v); filled++ } }
const challenge = await p.evaluate(() => /captcha|recaptcha|hcaptcha|turnstile|cf-challenge/i.test(document.documentElement.innerHTML))
const visible = fields.filter(f => !f.hidden)
const left = visible.filter(f => f.required && !(f.name in draft)).map(f => f.name)
const checkboxes = visible.filter(f => f.type === 'checkbox').length
await p.screenshot({ path: 'handover-test-venue-filled.png', fullPage: true })
const out = { venue: 'Sasha Test Venue (ours)', http: resp.status(), load_ms: loaded, fields_visible: visible.length, prefilled: filled,
  required_left_for_guest: left, checkboxes_left: checkboxes, challenge_seen: challenge,
  taps_left: left.length + checkboxes + 1 /* Book */, submitted: false }
console.log(JSON.stringify(out, null, 1))
await b.close()
