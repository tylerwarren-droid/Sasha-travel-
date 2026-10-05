"""CR 27 · THE GUESTCENTRIC HAND-OVER — a hotel's own HyperCommerce engine, two taps: ☐ "I accept the Terms" + Book Now.

    POST /api/booking/handover/guestcentric/rates   (keyed) the hotel's rates for a stay, each with its OWN terms and whether
                                                    it can be handed over (pay at the hotel, no card)
    POST /api/booking/handover/guestcentric         (keyed) the guest's chosen (rate, room) + their details → ONE link
    POST /api/booking/ops/handovers/rehearse-guestcentric   (founder only) READ-ONLY: a fictional guest, never Book Now

The founder's rules (CR 27, absolute), each enforced here:
  · every information field pre-filled (name, email, phone, country, address, city, zip, motive; a custom question the
    hotel adds — e.g. "Check-in Time" — from the guest's answer) or no link;
  · the "I accept the Terms" box is LEFT for the guest (Sasha never ticks consent; the offers box is never ticked) →
    2 taps: ☐ + Book Now;
  · ONLY a rate whose own terms say pay at the hotel and mention no card, prepayment, guarantee or deposit — anything
    else (or silence) is refused; and a card field or payment frame on the page → refused; payment providers' hosts are
    blocked in the cloud browser so a card form can never load in it; if a card page still appears after Book Now, the
    session ends at once and the guest finishes on the hotel's own page in their own browser;
  · the rate is the guest's choice — Sasha selects exactly the (rate, room) they named and checks the hotel's own
    Reservation Summary names it, or no link (CR 27: a loose match once picked the non-refundable rate);
  · the hotel's OWN engine only (its book.php?apikey / ?gc= link, engine_library), never a platform; real guests wait
    for the DPA like every hand-over.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from fastapi import Request

from . import engine_library as EL
from . import handover as HO
from . import venue_read as V

log = logging.getLogger("booking_signer.handover_guestcentric")

PAY_AT_HOTEL = re.compile(r"pay(ment)?\s+(at|in)\s+the\s+(hotel|property)|pay\s+(on|upon)\s+arrival|pay\s+at\s+check-?in|no\s+pre-?payment"
                          r"|pago\s+en\s+el\s+(hotel|alojamiento)|pagamento\s+no\s+(hotel|check-?in)|pagar\s+no\s+hotel", re.I)
CARD = re.compile(r"credit\s*card|debit\s*card|\bcards?\b|cart[aã]o|tarjeta|\bcarte\b|guarantee|garant[ií]a|garantia|pre-?pay|pay\s+now"
                  r"|deposit|dep[oó]sito|non-?\s?refundable|n[aã]o\s+reembols|no\s+reembols", re.I)
_REFNO = r"((?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,24})"     # a reference holds a digit (never "tion" from "reservation")
CONFIRMED = re.compile(r"\b(?:reservation|booking|confirmation)\s+(?:number|no\.?|code|reference|ref\.?|id)\s*[:#]?\s*" + _REFNO
                       + r"|\b(?:reserva|localizador|n[uú]mero\s+de\s+reserva)\b\s*[:#]?\s*" + _REFNO, re.I)
INFO = ("first_name", "last_name", "email", "phone_cc", "phone", "country", "address", "city", "zip")
FIELD = {"first_name": "first-name", "last_name": "last-name", "email": "email", "phone_cc": "country-code", "phone": "phone",
         "address": "address", "city": "city", "zip": "zip-code", "notes": "special-requests"}
GUEST_BOXES = {"accept-terms"}                 # the guest's to tick
NEVER_TICKED = {"notify-offers"}               # marketing consent: never ticked by Sasha
MOTIVES = ("Business", "Leisure", "A little of both")
#: (hotel's engine, rate) → (when read, its own terms) — the list Sasha offered the guest; the hand-over reuses terms read
#: in the last TERMS_FRESH seconds instead of reading them again (and reads them if not)
RATE_TERMS: Dict[Tuple[str, str], Tuple[float, str]] = {}
TERMS_FRESH = 15 * 60


def _engine_key(engine_url: str) -> str:
    u = urlsplit(engine_url)
    return f"{u.netloc}{u.path}?{u.query}"


def rate_ok(terms: str) -> Tuple[bool, str]:
    """A rate may be handed over only when its OWN terms say pay at the hotel and say nothing of a card or prepayment."""
    t = " ".join((terms or "").split())
    card = CARD.search(t)
    if card:
        return False, f"its terms mention “{card.group(0)}” — a card or prepayment step can't go through Kanoe's browser"
    if not PAY_AT_HOTEL.search(t):
        return False, "its terms don't say you pay at the hotel — so a card step can't be ruled out"
    return True, "its terms say you pay at the hotel, and mention no card"


def missing_info(guest: Dict[str, Any]) -> List[str]:
    return [k for k in INFO if not str(guest.get(k) or "").strip()]


# ── the page: the engine's own screens, driven over CDP ─────────────────────────────────────────────────────────

_RATES_JS = """() => [...document.querySelectorAll('button')].filter(b => b.innerText.trim() === 'Select').map((b, i) => {
  let single = b, c = b;
  while (c.parentElement) { c = c.parentElement;
    if ([...c.querySelectorAll('button')].filter(x => x.innerText.trim() === 'Select').length > 1) break; single = c; }
  let a = b, h2s = [];
  while (a.parentElement && !h2s.length) { a = a.parentElement; h2s = [...a.querySelectorAll('h2')]; }
  const room = single.querySelector('h3');
  const line = single.innerText.replace(/\\s+/g, ' ');
  return {i, rate: h2s.length === 1 ? h2s[0].innerText.trim() : null, room: room ? room.innerText.trim() : null,
          price: (line.match(/€\\s?[\\d.,]+\\s*\\/\\s*(total stay|per night)/) || [''])[0],
          cancel: (line.match(/(Free cancellation until [^.]*\\.|Non refundable)/i) || [''])[0]};
})"""

_RATE_DETAILS_JS = """(i) => {
  const b = [...document.querySelectorAll('button')].filter(x => x.innerText.trim() === 'Select')[i];
  let a = b, h2 = null; while (a.parentElement && !h2) { a = a.parentElement; h2 = a.querySelector('h2'); }
  if (!h2) return false;
  let c = h2; let link = null;
  while (c && !link) { link = [...c.querySelectorAll('a, button, span')].find(e => e.innerText.trim() === 'View details'); c = c.parentElement; }
  if (!link) return false;
  link.setAttribute('data-kanoe-rate-details', '1'); return true;
}"""

_GUEST_JS = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'; };
  const fields = [...document.querySelectorAll('input, select, textarea')].filter(vis).map(e => ({
    name: e.name || '', type: (e.type || e.tagName).toLowerCase(), value: e.type === 'checkbox' ? '' : (e.value || ''),
    checked: !!e.checked, autocomplete: e.autocomplete || '',
    label: ((e.labels && e.labels[0] && e.labels[0].innerText) || e.placeholder || e.getAttribute('aria-label') || '').trim()}));
  const custom = [...document.querySelectorAll('input[type=text]')].filter(vis).filter(e => !/^(first-name|last-name|email|country-code|phone|address|city|zip-code)$/.test(e.name))
    .map(e => { let l = e.closest('div'); let t = ''; for (let k = 0; k < 3 && l && !t; k++) { const lab = l.querySelector('label'); t = lab ? lab.innerText.trim() : ''; l = l.parentElement; } return {name: e.name, label: t, value: e.value}; });
  const combo = document.querySelector('[role=combobox]');
  const summary = (document.body.innerText.match(/Reservation\\s*Summary([\\s\\S]{0,400})/) || ['', ''])[1].replace(/\\s+/g, ' ');
  const motive = [...document.querySelectorAll('button')].filter(b => /^(Business|Leisure|A little of both)$/.test(b.innerText.trim()))
    .map(b => ({text: b.innerText.trim(), on: /bg-brand|active|selected/.test(b.className) || b.getAttribute('aria-pressed') === 'true'}));
  return {url: location.href, fields, custom, country: combo ? combo.innerText.trim() : null, summary, motive,
          frames: [...document.querySelectorAll('iframe')].map(f => f.src || ''), text: document.body.innerText.slice(0, 6000),
          html: ''};
}"""

_FILL_GC_JS = """(vals) => { const o = {};
  for (const [n, v] of Object.entries(vals)) {
    const el = document.querySelector('[name="' + n + '"]'); if (!el) { o[n] = null; continue; }
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement : HTMLInputElement;
    Object.getOwnPropertyDescriptor(proto.prototype, 'value').set.call(el, v);
    for (const ev of ['input', 'change', 'blur']) el.dispatchEvent(new Event(ev, {bubbles: true}));
    o[n] = el.value; }
  return o; }"""

_POINT_TWO_JS = """() => {
  if (!document.getElementById('kanoe-style')) {
    const st = document.createElement('style'); st.id = 'kanoe-style';
    st.textContent = '@keyframes kanoePulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.7)}70%{box-shadow:0 0 0 14px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}';
    document.head.appendChild(st);
  }
  const terms = document.querySelector('[name="accept-terms"]');
  const book = [...document.querySelectorAll('button')].filter(b => b.innerText.trim() === 'Book Now').pop();
  if (!terms || !book) return null;
  book.setAttribute('data-kanoe-book', '1');
  const row = terms.closest('label') || terms.parentElement;
  for (const el of [row, book]) { el.style.outline = '3px solid #22c55e'; el.style.outlineOffset = '3px'; el.style.animation = 'kanoePulse 1.6s infinite'; }
  row.scrollIntoView({block: 'center'});
  const tag = (id, text, el) => { let m = document.getElementById(id); if (!m) { m = document.createElement('div'); m.id = id; document.body.appendChild(m); }
    const r = el.getBoundingClientRect(); m.textContent = text;
    m.style.cssText = `position:fixed;left:${Math.max(6, Math.min(r.left, innerWidth - 150))}px;top:${Math.max(6, r.top - 34)}px;pointer-events:none;`
      + 'z-index:2147483647;background:#22c55e;color:#04210f;font:600 13px/1 -apple-system,system-ui,sans-serif;padding:7px 12px;border-radius:999px;box-shadow:0 4px 14px rgba(0,0,0,.25)'; };
  tag('kanoe-one', '\\u2460 Tick this box', row); tag('kanoe-two', '\\u2461 Then press Book Now', book);
  return {terms: (row.innerText || '').trim().slice(0, 140), book: book.innerText.trim()};
}"""

_WATCH_GC_JS = """() => {
  if (window.__kanoeWatching) return; window.__kanoeWatching = true;
  document.addEventListener('pointerdown', e => { try { window.__kanoeTap((e.target && (e.target.innerText || e.target.name || e.target.tagName) || '').slice(0, 40)); } catch (_) {} }, true);
  document.addEventListener('click', e => {
    const b = e.target && e.target.closest && e.target.closest('[data-kanoe-book]');
    if (!b) return;
    if (window.__kanoeReadOnly) { e.preventDefault(); e.stopImmediatePropagation(); }
    try { window.__kanoePress((b.innerText || '').trim()); } catch (_) {}
  }, true);
}"""


class GuestcentricPage(HO.PlaywrightPage):
    """The engine's screens: rates → (rate details) → Select → [extras] → /guest. It reads, fills and clicks; it decides nothing."""

    async def guard(self, read_only: bool) -> None:
        """Payment providers never load here (a card form can't appear in Kanoe's browser); read-only: no write leaves."""
        async def gate(route):
            r = route.request
            if HO._PAY_FRAME.search(r.url) or (read_only and r.method not in ("GET", "HEAD", "OPTIONS")):
                await route.abort()
            else:
                await route.continue_()
        await self.page.route("**/*", gate)
        if read_only:
            await self.page.add_init_script("window.__kanoeReadOnly = true")

    async def settle(self, ms: int = 15000) -> None:
        """Until the engine has drawn its rates (or its details form) — not a fixed wait; then cookies are rejected."""
        try:
            await self.page.wait_for_function("""() => [...document.querySelectorAll('button')].some(b => b.innerText.trim() === 'Select')
                || !!document.querySelector('[name="first-name"]') || /sorry/i.test(document.body.innerText)""", timeout=ms)
        except Exception:
            pass
        rej = self.page.get_by_role("button", name="Reject all Cookies")   # the privacy-preserving choice
        if await rej.count():
            await rej.first.click()
            await self.page.wait_for_timeout(250)

    async def rates(self) -> List[dict]:
        return await self.page.evaluate(_RATES_JS)

    async def rate_terms(self, i: int, search_url: str) -> str:
        if not await self.page.evaluate(_RATE_DETAILS_JS, i):
            return ""
        await self.page.locator('[data-kanoe-rate-details="1"]').first.click()
        try:
            await self.page.wait_for_url("**/rate/details/**", timeout=10000)
            await self.page.wait_for_timeout(600)
        except Exception:
            return ""
        text = " ".join((await self.page.evaluate("() => document.body.innerText")).split())
        await self.page.go_back()
        await self.settle()
        return text[text.find("Special Rates") + len("Special Rates"):] if "Special Rates" in text else text

    async def select(self, i: int) -> str:
        await self.page.get_by_role("button", name="Select", exact=True).nth(i).click()
        try:
            await self.page.wait_for_url(re.compile(r"/(extras|guest)"), timeout=12000)
        except Exception:
            return self.page.url
        if "/extras" in self.page.url:    # add-ons: none taken; its button only moves on to the details page
            await self.page.get_by_role("button", name="Book Now", exact=True).first.click()
            try:
                await self.page.wait_for_url(re.compile(r"/guest"), timeout=12000)
            except Exception:
                return self.page.url
        try:
            await self.page.wait_for_selector('[name="first-name"]', timeout=12000)
        except Exception:
            pass
        return self.page.url

    async def read_guest(self) -> dict:
        return await self.page.evaluate(_GUEST_JS)

    async def set_country(self, country: str) -> str:
        """The engine's country list (a combobox): opened in the page, the country typed, its own option chosen."""
        cb = self.page.locator("[role=combobox]").first
        if not await cb.count():
            return ""
        await self.page.evaluate("""() => { const c = document.querySelector('[role=combobox]');
            const i = c.querySelector('input') || c; i.focus(); for (const t of ['mousedown', 'mouseup', 'click'])
            c.dispatchEvent(new MouseEvent(t, {bubbles: true})); }""")
        await self.page.keyboard.type(country, delay=10)
        try:
            await self.page.wait_for_function("""(c) => [...document.querySelectorAll('[role=option]')]
                .some(o => o.innerText.trim().toLowerCase().startsWith(c.toLowerCase()))""", arg=country, timeout=1200)
        except Exception:
            pass
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(150)
        return (await cb.inner_text()).strip()

    async def set_motive(self, motive: str) -> None:
        await self.page.evaluate("""(m) => { const b = [...document.querySelectorAll('button')].find(x => x.innerText.trim() === m);
            if (b) b.click(); }""", motive)

    async def fill_named(self, vals: Dict[str, str]) -> Dict[str, Optional[str]]:
        return await self.page.evaluate(_FILL_GC_JS, vals)

    async def point_two(self) -> Optional[dict]:
        return await self.page.evaluate(_POINT_TWO_JS)

    async def fit(self, width: int, height: int) -> str:
        """The guest's frame size, then BOTH taps pointed at again (the terms box centred; Book Now sticks to the bottom)."""
        await self.page.set_viewport_size({"width": width, "height": height})
        await self.page.wait_for_timeout(150)
        p = await self.point_two()
        return (p or {}).get("book") or "Book Now"

    async def watch(self, on_tap, on_press, read_only, on_navigated) -> None:
        await self.page.expose_function("__kanoeTap", on_tap)
        await self.page.expose_function("__kanoePress", on_press)
        if read_only:
            await self.page.evaluate("window.__kanoeReadOnly = true")
        await self.page.add_init_script(f"({_WATCH_GC_JS})()")
        await self.page.evaluate(_WATCH_GC_JS)
        self.page.on("framenavigated", lambda fr: on_navigated() if fr == self.page.main_frame else None)

    async def answer(self) -> dict:
        await self.page.wait_for_timeout(5000)            # the SPA answers in place; give it its seconds
        g = await self.read_guest()
        return {"url": g["url"], "text": g["text"], "fields": g["fields"], "frames": g["frames"]}


PAGE_FACTORY: Any = GuestcentricPage


# ── the checks ──────────────────────────────────────────────────────────────────────────────────────────────────

def payment_on(seen: dict) -> Optional[str]:
    for src in seen.get("frames") or []:
        if src and HO._PAY_FRAME.search(src):
            return urlsplit(src).hostname
    for f in seen.get("fields") or []:
        if f.get("autocomplete", "").startswith("cc-") or HO._PAY_FIELD.search(f.get("name") or "") or HO._PAY_FIELD.search(f.get("label") or ""):
            return f.get("label") or f.get("name")
    return None


def summary_names(seen: dict, rate: str, room: Optional[str]) -> bool:
    s = (seen.get("summary") or "").lower()
    return bool(rate) and rate.lower() in s and (not room or room.lower() in s)


def empty_info(seen: dict) -> List[str]:
    """Visible information fields still empty (notes may stay empty; the two boxes are checked separately)."""
    out = [f["label"] or f["name"] for f in seen.get("fields") or []
           if f["type"] in ("text", "email", "tel", "select-one") and not f["value"] and f["name"] != "special-requests"]
    return out


def boxes_ok(seen: dict) -> Optional[str]:
    for f in seen.get("fields") or []:
        if f["type"] == "checkbox":
            if f["name"] in GUEST_BOXES and f["checked"]:
                return "the terms box is ticked — only the guest may tick it"
            if f["name"] in NEVER_TICKED and f["checked"]:
                return "the offers box is ticked — Sasha never ticks consent"
            if f["name"] not in GUEST_BOXES | NEVER_TICKED:
                return f"an unexpected box ({f['label'] or f['name']}) — no link"
    return None


def nights_line(checkin: date, checkout: date) -> str:
    n = (checkout - checkin).days
    a = f"{HO._DAYS[checkin.weekday()]} {checkin.day} {HO._MONTHS[checkin.month - 1]}"
    b = f"{HO._DAYS[checkout.weekday()]} {checkout.day} {HO._MONTHS[checkout.month - 1]}"
    return f"{a} – {b} · {n} night{'s' if n != 1 else ''}"


# ── the core ────────────────────────────────────────────────────────────────────────────────────────────────────

def _search_url(engine_url: str, stay: dict) -> str:
    url, carried = EL.build("Guestcentric", engine_url, checkin=stay["checkin"], checkout=stay["checkout"],
                            rooms=stay.get("rooms", 1), adults=stay.get("adults", 2), children=stay.get("children", 0))
    if not carried:
        raise HO.Refused("not_the_engine", "that link isn't the hotel's own booking engine (its book.php?apikey or ?gc= link)")
    return url


def _engine_ok(engine_url: str) -> None:
    u = urlsplit(engine_url or "")
    if u.scheme != "https" or V.platform_of(engine_url):
        raise HO.Refused("not_the_engine", "only the hotel's own booking engine, over https, is handed over")


async def list_rates(engine_url: str, stay: dict) -> List[dict]:
    """Every rate for the stay with its own terms and whether it can be handed over. No guest data involved."""
    _engine_ok(engine_url)
    url = _search_url(engine_url, stay)
    s = await HO.BB.create("gc-rates")
    page = PAGE_FACTORY()
    try:
        await page.connect(s["connectUrl"])
        await page.guard(read_only=True)
        await page.goto(url)
        await page.settle()
        rates = await page.rates()
        terms_by_rate: Dict[str, str] = {}
        for r in rates:
            if r["rate"] and r["rate"] not in terms_by_rate:
                terms_by_rate[r["rate"]] = await page.rate_terms(r["i"], url)
                RATE_TERMS[(_engine_key(engine_url), r["rate"])] = (HO.CLOCK(), terms_by_rate[r["rate"]])
        out = []
        for r in rates:
            ok, why = rate_ok(terms_by_rate.get(r["rate"] or "", ""))
            out.append({**r, "eligible": ok, "why": why, "terms": terms_by_rate.get(r["rate"] or "", "")[:600]})
        return out
    finally:
        await page.close()
        await HO.BB.release(s["id"])


async def open_gc_handover(*, engine_url: str, stay: dict, rate: str, room: Optional[str], guest: dict, hotel: str,
                           account: Optional[str], read_only: bool, fictional: bool, return_to: Optional[str] = None) -> dict:
    if not HO.configured():
        raise HO.Refused("cloud_browser_not_configured", "the live hand-over isn't set up on this server (BROWSERBASE_API_KEY)")
    if not read_only and not fictional and os.getenv("BROWSERBASE_DPA", "").strip() != "signed":
        raise HO.Refused("no_dpa", "a real guest's details don't go through the cloud browser until Kanoe has a signed data-processing "
                                   "agreement with it")
    _engine_ok(engine_url)
    gone = missing_info(guest)
    if gone:   # asked BEFORE any session: "every information field pre-filled, or no link"
        raise HO.Refused("missing_info", "Sasha needs these first: " + ", ".join(gone).replace("_", " "))
    url = _search_url(engine_url, stay)
    t0 = HO.CLOCK()
    hid = uuid.uuid4().hex[:12]
    rec: Dict[str, Any] = {"id": hid, "token": HO._token(), "account_id": account, "form_id": None, "venue": hotel,
                           "page_url": url, "host": urlsplit(url).hostname, "read_only": read_only, "test": False,
                           "state": "filling", "created_at": HO.NOW().isoformat(), "taps": 0, "tapped": [],
                           "return_to": HO._return_ok(return_to), "request": None, "steps": 2, "engine": "Guestcentric",
                           "taps_left": 2, "rate": rate, "room": room, "press_is_final": True,
                           "summary": {"venue": hotel, "day": nights_line(stay["checkin"], stay["checkout"]), "time": "",
                                       "party": f"{stay.get('adults', 2)} adult{'s' if stay.get('adults', 2) != 1 else ''}",
                                       "name": f"{guest['first_name']} {guest['last_name']}"},
                           "fallback_link": url}
    lap = HO._laps(rec, t0)
    s = await HO.BB.create(f"gc-handover:{hid}")
    lap("session")
    rec["session_id"] = s["id"]
    page = PAGE_FACTORY()
    try:
        await page.connect(s["connectUrl"])
        await page.guard(read_only)
        lap("connect")
        await page.goto(url)
        await page.settle()
        lap("page")
        rates = await page.rates()
        hits = [r for r in rates if r["rate"] == rate and (room is None or r["room"] == room)]
        if len(hits) != 1:
            raise HO.Refused("rate_not_found", f"the hotel doesn't show exactly one “{rate}”{' – ' + room if room else ''} for these dates "
                                               f"({len(hits)} found) — no link")
        cached = RATE_TERMS.get((_engine_key(engine_url), rate))
        if cached and HO.CLOCK() - cached[0] < TERMS_FRESH:
            terms = cached[1]                    # read minutes ago, when Sasha offered the guest this rate
        else:
            terms = await page.rate_terms(hits[0]["i"], url)
            RATE_TERMS[(_engine_key(engine_url), rate)] = (HO.CLOCK(), terms)
        ok, why = rate_ok(terms)
        rec["rate_terms"] = terms[:600]
        if not ok:
            raise HO.Refused("card_rate", f"“{rate}” can't be handed over: {why}. The link to the hotel's own page instead: {url}")
        rates = await page.rates()          # the list again (the terms page was visited); the same pair, by name
        hits = [r for r in rates if r["rate"] == rate and (room is None or r["room"] == room)]
        if len(hits) != 1:
            raise HO.Refused("rate_not_found", "the rate list changed while Sasha read it — no link")
        where = await page.select(hits[0]["i"])
        lap("rate")
        if "/guest" not in where:
            raise HO.Refused("unexpected_step", "the hotel's engine didn't open its details page after the rate — no link")
        seen = await page.read_guest()
        pay = payment_on(seen)
        if pay:
            raise HO.Refused("payment_step", f"the details page asks for payment ({pay}) — never through Kanoe's browser")
        for _ in range(6):                      # the summary card can draw after the form (fast from the EU server)
            if summary_names(seen, rate, room):
                break
            await asyncio.sleep(0.8)
            seen = await page.read_guest()
        if not summary_names(seen, rate, room):
            shows = (seen.get("summary") or "nothing")[:160]
            log.warning("[gc-handover] %s summary mismatch: wanted %s / %s, page shows: %s", hid, rate, room, shows)
            raise HO.Refused("wrong_rate", f"the hotel's Reservation Summary doesn't name “{rate}” (it shows: {shows}) — no link")
        lap("details_page")
        shown = await page.set_country(guest["country"])
        if guest["country"].lower() not in shown.lower():
            raise HO.Refused("not_all_prefilled", f"their country list didn't take “{guest['country']}” — no link")
        lap("country")
        await page.set_motive(guest.get("motive") or "Leisure")
        vals = {FIELD[k]: str(guest[k]) for k in INFO if k in FIELD}
        if guest.get("notes"):
            vals[FIELD["notes"]] = str(guest["notes"])
        for c in seen.get("custom") or []:      # the hotel's own extra questions, from the guest's answers only
            lab = (c.get("label") or "").lower()
            if re.search(r"check-?in time|arrival", lab) and guest.get("arrival_time") and c.get("name"):
                vals[c["name"]] = str(guest["arrival_time"])
        lap("motive")
        held = await page.fill_named(vals)
        bad = [n for n, v in vals.items() if (held.get(n) or "") != v]
        if bad:
            raise HO.Refused("not_all_prefilled", f"their form didn't take Sasha's value for {', '.join(bad)} — no link")
        seen = await page.read_guest()
        empty = empty_info(seen)
        if empty:
            raise HO.Refused("not_all_prefilled", f"not every information field could be filled ({', '.join(empty)}) — no link")
        box = boxes_ok(seen)
        if box:
            raise HO.Refused("boxes", box)
        if payment_on(seen):
            raise HO.Refused("payment_step", "the details page asks for payment — never through Kanoe's browser")
        rec["filled"] = [{"name": n, "label": n, "value": v} for n, v in vals.items()] + [{"name": "country", "label": "Country", "value": shown}]
        lap("fields_checked")
        pointed = await page.point_two()
        if not pointed:
            raise HO.Refused("unexpected_step", "the terms box or Book Now isn't where it should be — no link")
        rec["book_label"] = pointed["book"]
        rec["terms_label"] = pointed["terms"]
        rec["_nav"] = asyncio.Event()
        _, live = await asyncio.gather(
            page.watch(lambda what: HO._tap(rec, what), lambda label: HO._press(rec, label), read_only, lambda: HO._navigated(rec)),
            HO.BB.live_urls(s["id"]))
        lap("live_view")
        fs = (live.get("pages") or [{}])[0].get("debuggerFullscreenUrl") or live.get("debuggerFullscreenUrl")
        rec.update(live_url=f"{fs}&navbar=false" if "?" in (fs or "") else fs, state="ready",
                   ready_ms=round((HO.CLOCK() - t0) * 1000), ready_at=HO.NOW().isoformat())
        if read_only:
            rec["_screenshot"] = await page.page.screenshot(full_page=True) if hasattr(page, "page") and page.page else b""
    except HO.Refused:
        await page.close()
        await HO.BB.release(s["id"])
        raise
    except Exception as e:
        await page.close()
        await HO.BB.release(s["id"])
        log.warning("[gc-handover] %s failed: %s", hid, e)
        raise HO.Refused("handover_failed", f"the cloud browser couldn't prepare the hotel's page ({type(e).__name__}) — no link") from None
    rec["_page"] = page
    rec["_watch"] = asyncio.ensure_future(_watch(rec))
    HO.HANDOVERS[hid] = rec
    log.info("[gc-handover] %s ready in %sms: %s / %s (read_only=%s)", hid, rec["ready_ms"], rate, room, read_only)
    return rec


async def _watch(rec: dict) -> None:
    try:
        await asyncio.wait_for(rec["_nav"].wait(), timeout=HO.SESSION_SECONDS - 30)
    except asyncio.TimeoutError:
        await HO._end(rec, "expired", "no one pressed Book Now within 10 minutes; nothing was sent")
        return
    if rec["read_only"]:
        await HO._end(rec, "read_only_stopped", "Book Now was pressed and STOPPED in the page (read-only): nothing was sent")
        return
    try:
        seen = await rec["_page"].answer()
    except Exception as e:
        seen = {"text": "", "url": None, "fields": [], "frames": []}
        log.warning("[gc-handover] %s answer: %s", rec["id"], e)
    await finish(rec, seen)


async def finish(rec: dict, seen: dict) -> None:
    rec["press_to_answer_ms"] = round((HO.CLOCK() - rec["_pressed"]) * 1000)
    if rec.get("_opened") is not None:
        rec["open_to_booked_s"] = round(HO.CLOCK() - rec["_opened"], 1)
    pay = payment_on(seen)
    text = " ".join((seen.get("text") or "").split())[:4000]
    rec.update(answer_text=text, answered_at=HO.NOW().isoformat())
    if pay:   # a card page after all: Kanoe's browser closes at once; the guest finishes on the hotel's page, in theirs
        rec["say"] = ("The hotel asked for a card at the last step — Kanoe never handles cards, so I've closed my copy. Finish on "
                      f"their own page: {rec['fallback_link']}")
        await HO._end(rec, "card_page", rec["say"])
        return
    m = CONFIRMED.search(text)
    ref = (m.group(1) or m.group(2)) if m else None
    booked = bool(m) and re.search(r"confirm|thank you|obrigad|gracias|reserva\s+confirmada", text, re.I) is not None
    rec.update(reference=ref, state="booked" if booked else "answered",
               say=(f"✅ Booked — {rec['venue']}" + (f", ref {ref}" if ref else "") + ". The hotel's page confirms it."
                    if booked else "Sent — the hotel's page doesn't say it's confirmed; it's a request until they confirm."))
    for fn in list(HO.ON_BOOKED):
        try:
            await fn(HO._public(rec, ops_view=True))
        except Exception as e:
            log.warning("[gc-handover] %s ON_BOOKED: %s", rec["id"], e)
    await HO._release(rec)


# ── the routes ──────────────────────────────────────────────────────────────────────────────────────────────────

def _stay(body: dict) -> dict:
    ci, co = date.fromisoformat(str(body["checkin"])), date.fromisoformat(str(body["checkout"]))
    if co <= ci:
        raise ValueError("checkout must be after checkin")
    return {"checkin": ci, "checkout": co, "adults": int(body.get("adults", 2)), "children": int(body.get("children", 0)),
            "rooms": int(body.get("rooms", 1))}


async def _robots(url: str) -> bool:
    return await HO._robots_ok(url)


@HO.router.post("/handover/guestcentric/rates")
async def route_rates(request: Request):
    try:
        body = await request.json()
        stay = _stay(body)
    except Exception:
        return HO._no(400, "malformed", "send {engine_url, checkin, checkout, adults, children, rooms}")
    if not await _robots(body.get("engine_url") or ""):
        return HO._no(422, "robots", "the hotel's robots.txt does not allow it")
    try:
        rates = await list_rates(body["engine_url"], stay)
    except HO.Refused as e:
        return HO._no(422, e.rule, e.say)
    return {"ok": True, "rates": [{k: r[k] for k in ("rate", "room", "price", "cancel", "eligible", "why")} for r in rates]}


@HO.router.post("/handover/guestcentric")
async def route_handover(request: Request):
    from .account import account_for
    try:
        body = await request.json()
        stay = _stay(body)
    except Exception:
        return HO._no(400, "malformed", "send {engine_url, hotel, checkin, checkout, adults, rate, room, guest, return_to}")
    if not await _robots(body.get("engine_url") or ""):
        return HO._no(422, "robots", "the hotel's robots.txt does not allow it")
    try:
        rec = await open_gc_handover(engine_url=body["engine_url"], stay=stay, rate=str(body.get("rate") or ""), room=body.get("room"),
                                     guest=body.get("guest") or {}, hotel=str(body.get("hotel") or urlsplit(body["engine_url"]).hostname),
                                     account=account_for(request), read_only=False, fictional=False, return_to=body.get("return_to"))
    except HO.Refused as e:
        return HO._no(422, e.rule, e.say)
    return {"ok": True, "handover_id": rec["id"], "view_url": HO.view_url(rec), "ready_ms": rec["ready_ms"], "taps_left": 2,
            "say": f"I've filled in {rec['venue']}'s own booking page — every detail, your “{rec['rate']}” rate. Two taps left: tick "
                   f"“I accept the Terms”, then press “{rec['book_label']}”. {HO.view_url(rec)}"}


FICTIONAL = {"first_name": "Prueba", "last_name": "Sasha", "email": "prueba@example.com", "phone_cc": "+34", "phone": "600000000",
             "country": "Spain", "address": "Calle de Ejemplo 12", "city": "Madrid", "zip": "28013", "motive": "Leisure",
             "arrival_time": "15:00", "notes": "Prueba de Kanoe (ficticia)."}


@HO.ops.post("/handovers/rehearse-guestcentric")
async def route_rehearse(request: Request):
    """READ-ONLY, always: a fictional guest on a real hotel's engine, filled up to the last two taps; Book Now can't send."""
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    try:
        body = await request.json()
        stay = _stay(body)
    except Exception:
        return HO._no(400, "malformed", "send {engine_url, hotel, checkin, checkout, adults, rate, room}")
    if not await _robots(body.get("engine_url") or ""):
        return HO._no(422, "robots", "the hotel's robots.txt does not allow it")
    try:
        rec = await open_gc_handover(engine_url=body["engine_url"], stay=stay, rate=str(body.get("rate") or ""), room=body.get("room"),
                                     guest=FICTIONAL, hotel=str(body.get("hotel") or urlsplit(body["engine_url"]).hostname),
                                     account=None, read_only=True, fictional=True, return_to=body.get("return_to"))
    except HO.Refused as e:
        return HO._no(422, e.rule, e.say)
    rec["rehearsal_view"] = True        # the guest page can be opened to rehearse it; its last press is blocked
    return {"ok": True, **HO._public(rec, ops_view=True), "rate_terms": rec.get("rate_terms"),
            "operator_url_read_only": rec.get("live_url"),
            "screenshot_png_b64": base64.b64encode(rec.get("_screenshot") or b"").decode()}


__all__ = ["rate_ok", "list_rates", "open_gc_handover", "finish", "payment_on", "summary_names", "empty_info", "boxes_ok"]
