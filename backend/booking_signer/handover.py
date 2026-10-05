"""CR 23 · THE LIVE HAND-OVER — Sasha fills a venue's OWN booking form in a cloud browser; the guest presses Book.

    POST /api/booking/forms/{form_id}/handover   (keyed) a PREPARED form (Sasha 89's read-back) → the guest's link, or a refusal
    GET  /api/booking/handover/{hid}?t=…          the guest's page: the live view, Sasha's line, then "✅ Booked" and back
    GET  /api/booking/handover/{hid}/status?t=…   what that page polls
    GET  /api/booking/ops/handovers               (founder only) every hand-over: state, taps, seconds; a live one's
                                                  operator_url is the interactive live view — the operator takes over there
    POST /api/booking/ops/handovers/rehearse      (founder only) our test venue with a fictional guest, or an approved venue's
                                                  own form READ-ONLY (nothing can be sent: every non-GET request is blocked)
    POST /api/booking/ops/handovers/{hid}/end     (founder only) release the cloud session now

THE FOUNDER'S LAST-PRESS RULES (absolute), each enforced here:
  · every field pre-filled, or we don't send that link — after filling, the page's own validity check must pass and every
    required visible field must hold Sasha's value; otherwise the session is released and the caller gets a refusal;
  · land on the final step — a two-step form's first step (the day) is sent by Sasha; the guest sees only the last page;
  · straight back to Sasha with "✅ Booked" — the press is caught in the page, their answer page read the moment it loads
    (form rung's reading: only a page that restates the booking with a yes confirms); ON_BOOKED hooks tell her channels;
  · an operator can take the session: the same cloud session's interactive live view, from the ops console;
  · venues' OWN sites only — the form rung's map (test venue, or a founder-approved host), never a platform host or a
    platform frame; never a payment step (a card/IBAN field or a payment provider's frame anywhere → refused);
  · a CAPTCHA → refused (Browserbase's solver is switched OFF); a box agreeing to terms → refused (it is the guest's).

Browserbase: sessions in eu-central-1 (Frankfurt), recording and logging OFF, 10 minutes, released when done.
⚠ Their DPA exists only on the Scale plan (CR 23 readout): until one is signed, only fictional details go through it —
REAL guests are refused unless BROWSERBASE_DPA=signed is set (the founder's switch, after signing).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from html import escape
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import form_rung as FR
from . import venue_read as V
from .account import account_for

log = logging.getLogger("booking_signer.handover")
router = APIRouter(tags=["booking-handover"])
ops = APIRouter(prefix="/ops", tags=["booking-ops"])

API = "https://api.browserbase.com/v1"
REGION = "eu-central-1"
SESSION_SECONDS = 600
VIEWPORT = {"width": 390, "height": 844}            # a phone: most guests open it from WhatsApp
RETURN_HOSTS = ("kanoe.ai", "wa.me", "whatsapp.com")   # "back to Sasha" goes only to her own places
HANDOVERS: Dict[str, Dict[str, Any]] = {}          # this server's hand-overs (one worker); outcomes also go to the form store
ON_BOOKED: List[Callable[[dict], Awaitable[Any]]] = []   # Sasha's channels register here: "✅ Booked" on WhatsApp / the chat
NOW = lambda: datetime.now(timezone.utc)
CLOCK = time.monotonic

# a payment step, by field or by frame — never through a browser we host (PCI)
_PAY_FIELD = re.compile(r"\b(cc-|card|tarjeta|cart[aã]o|carte|kreditkarte|cvv|cvc|csc|iban|caducidad|expir|security.?code)", re.I)
_PAY_FRAME = re.compile(r"stripe\.com|adyen|redsys|paypal|braintree|checkout\.com|mollie|sumup|square(up)?\.com|worldpay|klarna", re.I)


class Refused(Exception):
    def __init__(self, rule: str, say: str) -> None:
        super().__init__(say)
        self.rule, self.say = rule, say


def configured() -> bool:
    return bool(os.getenv("BROWSERBASE_API_KEY", "").strip())


def status() -> dict:
    """For /health: never a value."""
    return {"configured": configured(), "region": REGION, "recording": False, "captcha_solving": False,
            "real_guests": os.getenv("BROWSERBASE_DPA", "").strip() == "signed"}


# ── Browserbase (the REST side): injectable ─────────────────────────────────────────────────────────────────────────

class Browserbase:
    async def _call(self, method: str, path: str, json: Optional[dict] = None) -> dict:
        from .http_pool import request   # Sasha 149 · one kept-alive client per loop
        key = os.getenv("BROWSERBASE_API_KEY", "").strip()
        r = await request(method, f"{API}{path}", timeout=20.0, json=json, headers={"X-BB-API-Key": key})
        if r.status_code >= 400:
            raise Refused("cloud_browser_unavailable", f"the cloud browser answered HTTP {r.status_code}; nothing was filled")
        return r.json() if r.content else {}

    async def create(self, purpose: str) -> dict:
        body = {"region": REGION, "timeout": SESSION_SECONDS, "keepAlive": False,
                "browserSettings": {"recordSession": False, "logSession": False, "solveCaptchas": False, "blockAds": True,
                                    "viewport": VIEWPORT},
                "userMetadata": {"kanoe": purpose}}
        pid = os.getenv("BROWSERBASE_PROJECT_ID", "").strip()
        if pid:
            body["projectId"] = pid
        return await self._call("POST", "/sessions", body)

    async def live_urls(self, sid: str) -> dict:
        return await self._call("GET", f"/sessions/{sid}/debug")

    async def release(self, sid: str) -> None:
        try:
            await self._call("POST", f"/sessions/{sid}", {"status": "REQUEST_RELEASE"})
        except Exception as e:   # the session ends at its timeout anyway
            log.warning("[handover] release %s: %s", sid, e)


BB: Any = Browserbase()


# ── the page (Playwright over CDP): injectable ─────────────────────────────────────────────────────────────────────

_READ_JS = """() => {
  const vis = el => { const s = getComputedStyle(el); const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const frames = [...document.querySelectorAll('iframe')].map(f => f.src || '');
  const fields = [...document.querySelectorAll('input, select, textarea')].map(el => ({
    name: el.name || '', type: (el.type || el.tagName).toLowerCase(), autocomplete: el.autocomplete || '',
    required: !!el.required, visible: vis(el), empty: (el.type === 'checkbox' || el.type === 'radio') ? !el.checked : !el.value,
    value: (el.type === 'hidden') ? '' : (el.value || '') }));
  const form = [...document.forms].find(f => f.querySelectorAll('input:not([type=hidden]), select, textarea').length >= 3);
  return {url: location.href, frames, fields, valid: form ? form.checkValidity() : false, html: document.documentElement.outerHTML,
          text: (document.body && document.body.innerText || '').slice(0, 6000)};
}"""

_WATCH_JS = """() => {
  if (window.__kanoeWatching) return; window.__kanoeWatching = true;
  document.addEventListener('pointerdown', e => { try { window.__kanoeTap((e.target && (e.target.innerText || e.target.name || e.target.tagName) || '').slice(0, 40)); } catch (_) {} }, true);
  document.addEventListener('submit', e => {
    if (window.__kanoeReadOnly) { e.preventDefault(); e.stopImmediatePropagation(); }
    try { window.__kanoePress(e.submitter ? (e.submitter.innerText || e.submitter.value || '') : ''); } catch (_) {}
  }, true);
}"""

_FILL_JS = """(values) => {
  const form = [...document.forms].find(f => f.querySelectorAll('input:not([type=hidden]), select, textarea').length >= 3);
  const out = {};
  for (const [name, value] of Object.entries(values)) {
    const el = form && form.querySelector(`[name="${CSS.escape(name)}"]`);
    if (!el) { out[name] = null; continue; }
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement : HTMLInputElement;
    Object.getOwnPropertyDescriptor(proto.prototype, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true}));
    out[name] = el.value;
  }
  return out;
}"""

_POINT_JS = """(sel) => {
  const form = [...document.forms].find(f => f.querySelectorAll('input:not([type=hidden]), select, textarea').length >= 3);
  const bs = form ? form.querySelectorAll(sel) : []; const b = bs[bs.length - 1];
  if (!b) return '';
  if (!document.getElementById('kanoe-style')) {
    const st = document.createElement('style'); st.id = 'kanoe-style';
    st.textContent = '@keyframes kanoePulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.7)}70%{box-shadow:0 0 0 14px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}'
      + '@keyframes kanoeBob{0%,100%{transform:translate(-50%,0)}50%{transform:translate(-50%,-5px)}}';
    document.head.appendChild(st);
  }
  b.style.outline = '3px solid #22c55e'; b.style.outlineOffset = '3px'; b.style.animation = 'kanoePulse 1.6s infinite';
  b.scrollIntoView({block: 'center', inline: 'center'});
  let m = document.getElementById('kanoe-press');
  if (!m) { m = document.createElement('div'); m.id = 'kanoe-press'; document.body.appendChild(m); }
  const r = b.getBoundingClientRect(), w = 112, below = r.bottom + 46 < innerHeight;
  m.textContent = below ? '\u2191 Press here' : 'Press here \u2193';
  const x = Math.min(Math.max(r.left + r.width / 2, w / 2 + 6), document.documentElement.clientWidth - w / 2 - 6);
  const y = below ? r.bottom + scrollY + 10 : r.top + scrollY - 40;
  m.style.cssText = `position:absolute;left:${x + scrollX}px;top:${y}px;width:${w}px;transform:translateX(-50%);`
    + 'pointer-events:none;z-index:2147483647;background:#22c55e;color:#04210f;font:600 14px/1 -apple-system,system-ui,sans-serif;'
    + 'text-align:center;padding:8px 0;border-radius:999px;box-shadow:0 4px 14px rgba(0,0,0,.25);animation:kanoeBob 1.4s ease-in-out infinite';
  return (b.tagName === 'BUTTON' ? b.innerText : b.value || '').trim();
}"""

_SUBMIT = "button[type=submit], input[type=submit], button:not([type])"


class PlaywrightPage:
    """One cloud page, driven over CDP. Nothing here decides anything: it reads, fills, clicks, and reports."""

    def __init__(self) -> None:
        self.pw = self.browser = self.page = None

    async def connect(self, connect_url: str) -> None:
        from playwright.async_api import async_playwright
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.connect_over_cdp(connect_url)
        ctx = self.browser.contexts[0]
        self.page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    async def goto(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)

    async def read(self) -> dict:
        return await self.page.evaluate(_READ_JS)

    async def fill_all(self, values: Dict[str, str]) -> Dict[str, str]:
        """Every field in ONE round trip: the element's own value setter (so a framework's form sees it), then the input
        and change events a typing guest would fire; what each field holds afterwards comes back."""
        return await self.page.evaluate(_FILL_JS, values)

    async def advance(self) -> None:
        """A first step's own button (the day only, not the booking), then its next page."""
        async with self.page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
            await self.page.locator(f"form {_SUBMIT}").first.click()

    async def point_at_book(self) -> str:
        """The form's own Book button, centred in view, outlined, with Sasha's pulsing "Press here" just above it — one
        round trip; its words come back. The marker ignores taps (they reach the button) and sends nothing anywhere."""
        return await self.page.evaluate(_POINT_JS, _SUBMIT)

    async def fit(self, width: int, height: int) -> str:
        """The cloud browser resized to the guest's frame (so the live view is 1:1 and the button is on screen), then the
        button pointed at again."""
        await self.page.set_viewport_size({"width": width, "height": height})
        return await self.point_at_book()

    async def snapshot(self) -> bytes:
        """What the live view will show, as a JPEG — the page shows it while Browserbase's viewer starts (a few seconds)."""
        return await self.page.screenshot(type="jpeg", quality=72)

    async def watch(self, on_tap: Callable[[str], None], on_press: Callable[[str], None], read_only: bool,
                    on_navigated: Callable[[], None]) -> None:
        await self.page.expose_function("__kanoeTap", on_tap)
        await self.page.expose_function("__kanoePress", on_press)
        if read_only:   # nothing can leave: the press is cancelled in the page AND every non-GET request is aborted
            await self.page.add_init_script("window.__kanoeReadOnly = true")
            await self.page.evaluate("window.__kanoeReadOnly = true")

            async def gate(route):
                if route.request.method != "GET" or (route.request.is_navigation_request() and route.request.frame == self.page.main_frame):
                    await route.abort()
                else:
                    await route.continue_()
            await self.page.route("**/*", gate)
        await self.page.add_init_script(f"({_WATCH_JS})()")
        await self.page.evaluate(_WATCH_JS)
        self.page.on("framenavigated", lambda fr: on_navigated() if fr == self.page.main_frame else None)

    async def answer(self) -> dict:
        await self.page.wait_for_load_state("domcontentloaded", timeout=20000)
        return await self.read()

    async def screenshot(self) -> bytes:
        return await self.page.screenshot(full_page=True)

    async def close(self) -> None:
        for x in (self.browser, self.pw):
            try:
                if x is self.pw and x:
                    await x.stop()
                elif x:
                    await x.close()
            except Exception:
                pass


PAGE_FACTORY: Callable[[], Any] = PlaywrightPage


# ── the checks: one page, as the live browser shows it ────────────────────────────────────────────────────────────

def check_page(seen: dict, m: dict, page_url: str) -> List[dict]:
    """The page's booking form through the form rung's own reading — or a Refused naming why no link is sent."""
    url = seen.get("url") or page_url
    if V.platform_of(url):
        raise Refused("platform", "that page is a booking platform's — Sasha only hands over a venue's own website")
    if FR.reg_host(url) != FR.reg_host(page_url):
        raise Refused("left_the_venue", "the form moved to another website — Sasha only hands over the venue's own site")
    for src in seen.get("frames") or []:
        if src and V.platform_of(src):
            raise Refused("platform", f"the booking form sits in a booking platform's frame ({urlsplit(src).hostname}) — never handed over")
        if src and _PAY_FRAME.search(src):
            raise Refused("payment_step", "the page has a payment step — never through a browser Kanoe hosts; you'd pay on their page yourself")
    for x in seen.get("fields") or []:
        if x.get("visible") and (x.get("autocomplete", "").startswith("cc-") or _PAY_FIELD.search(x.get("name") or "")):
            raise Refused("payment_step", "the form asks for a card or bank detail — never through a browser Kanoe hosts")
    live = FR.read_form(seen.get("html") or "", url)
    if "why" in live:
        raise Refused("no_form", f"no booking form on the page ({live['why']})")
    fields = FR.roles_for(live, m)
    if any(x["role"] == "challenge" for x in fields):
        raise Refused("captcha", "their form has a CAPTCHA — Sasha never solves one, so no link")
    if any(x["role"] == "consent" and x["required"] for x in fields):
        raise Refused("consent_box", "their form needs a box ticked to accept their terms — that box is yours, so Sasha can't hand "
                                     "over a fully filled form")
    other = [x["name"] for x in fields if x["role"] == "other" and x["required"]]
    if other:
        raise Refused("unmapped_field", f"their form requires a field Sasha has no value for ({', '.join(other)}) — no link")
    return fields


def still_empty(seen: dict, fields: List[dict]) -> List[str]:
    """Required, visible fields still empty after filling — any one means no link."""
    traps = {x["name"] for x in fields if x["role"] in ("trap", "hidden")}
    return [x["name"] for x in seen.get("fields") or [] if x.get("required") and x.get("visible") and x.get("empty")
            and x.get("name") not in traps]


def _token() -> str:
    return secrets.token_urlsafe(32)


def _return_ok(url: Optional[str]) -> Optional[str]:
    h = (urlsplit(url or "").hostname or "").lower()
    return url if url and urlsplit(url).scheme == "https" and any(h == d or h.endswith("." + d) for d in RETURN_HOSTS) else None


def view_url(rec: dict) -> str:
    return f"{FR.public_base()}/api/booking/handover/{rec['id']}?t={rec['token']}"


# ── the core: fill, land, hand over, watch ────────────────────────────────────────────────────────────────────────

async def open_handover(*, page_url: str, m: dict, step1: List[dict], step2: List[dict], venue: str, account: Optional[str],
                        form_id: Optional[str], read_only: bool, return_to: Optional[str] = None, request: Optional[dict] = None,
                        fictional: bool = False) -> dict:
    """→ the hand-over record (ready, with its link), or Refused. The session is released on any refusal."""
    if not configured():
        raise Refused("cloud_browser_not_configured", "the live hand-over isn't set up on this server (BROWSERBASE_API_KEY)")
    if not m.get("test") and not read_only and not fictional and os.getenv("BROWSERBASE_DPA", "").strip() != "signed":
        raise Refused("no_dpa", "a real guest's details don't go through the cloud browser until Kanoe has a signed data-processing "
                                "agreement with it — Sasha sends the form herself after your yes instead")
    if V.platform_of(page_url):
        raise Refused("platform", "that page is a booking platform's — Sasha only hands over a venue's own website")
    if read_only and m.get("test") is False and step2:
        raise Refused("read_only_two_steps", "a read-only run never sends a first step, so a two-step form stops at step 1")
    t0 = CLOCK()
    hid = uuid.uuid4().hex[:12]
    rec: Dict[str, Any] = {"id": hid, "token": _token(), "account_id": account, "form_id": form_id, "venue": venue,
                           "page_url": page_url, "host": urlsplit(page_url).hostname, "read_only": read_only, "test": bool(m.get("test")),
                           "state": "filling", "created_at": NOW().isoformat(), "taps": 0, "tapped": [], "return_to": _return_ok(return_to),
                           "request": request, "steps": 2 if step2 else 1}
    lap = _laps(rec, t0)
    s = await BB.create(f"handover:{hid}")
    lap("session")
    rec["session_id"] = s["id"]
    page = PAGE_FACTORY()
    try:
        await page.connect(s["connectUrl"])
        lap("connect")
        await page.goto(page_url)
        lap("page")
        fields = check_page(await page.read(), m, page_url)
        names = {x["name"] for x in fields}
        gone = [x["name"] for x in step1 if x["name"] not in names]
        if gone:
            raise Refused("form_changed", f"their form no longer has {', '.join(gone)} — no link")
        rec["filled"] = await _fill(page, step1, fields)
        seen = await page.read()
        if step2:
            empty = still_empty(seen, fields)
            if empty or not seen.get("valid"):
                raise Refused("not_all_prefilled", f"step 1 wasn't fully filled ({', '.join(empty) or 'their own check failed'}) — no link")
            await page.advance()                                    # the day goes; the booking is the guest's press on the last step
            fields = check_page(await page.read(), m, page_url)
            names = {x["name"] for x in fields}
            gone = [x["name"] for x in step2 if x["name"] not in names]
            if gone:
                raise Refused("form_changed", f"their details page has no {', '.join(gone)} — no link")
            rec["filled"] += await _fill(page, step2, fields)
            seen = await page.read()
        empty = still_empty(seen, fields)
        if empty or not seen.get("valid"):
            raise Refused("not_all_prefilled", f"not every field could be filled ({', '.join(empty) or 'their own check failed'}) — "
                                               "so Sasha doesn't send the link")
        lap("fill")
        rec["book_label"] = await page.point_at_book()
        rec["_nav"] = asyncio.Event()                               # before the watch: a press can't race it
        _, live = await asyncio.gather(
            page.watch(lambda what: _tap(rec, what), lambda label: _press(rec, label), read_only, lambda: _navigated(rec)),
            BB.live_urls(s["id"]))
        lap("live_view")
        fs = (live.get("pages") or [{}])[0].get("debuggerFullscreenUrl") or live.get("debuggerFullscreenUrl")
        rec.update(live_url=f"{fs}&navbar=false" if "?" in (fs or "") else fs, state="ready",
                   ready_ms=round((CLOCK() - t0) * 1000), ready_at=NOW().isoformat())
        if read_only:
            rec["screenshot_sha256"] = hashlib.sha256(shot := await page.screenshot()).hexdigest()
            rec["_screenshot"] = shot
    except Refused:
        await page.close()
        await BB.release(s["id"])
        raise
    except Exception as e:
        await page.close()
        await BB.release(s["id"])
        log.warning("[handover] %s failed: %s", hid, e)
        raise Refused("handover_failed", f"the cloud browser couldn't prepare their form ({type(e).__name__}) — no link") from None
    rec["_page"] = page
    rec["_watch"] = asyncio.ensure_future(_watch(rec))
    HANDOVERS[hid] = rec
    log.info("[handover] %s ready in %sms: %s (%s fields, read_only=%s)", hid, rec["ready_ms"], rec["host"], len(rec["filled"]), read_only)
    return rec


def _laps(rec: dict, t0: float) -> Callable[[str], None]:
    """Where the seconds go before the link exists (ms since the last mark) — the ops log's breakdown."""
    rec["timings_ms"], last = {}, [t0]

    def lap(name: str) -> None:
        now = CLOCK()
        rec["timings_ms"][name] = round((now - last[0]) * 1000)
        last[0] = now
    return lap


async def _fill(page, values: List[dict], fields: List[dict]) -> List[dict]:
    roles = {x["name"]: x for x in fields}
    held = await page.fill_all({v["name"]: str(v["value"]) for v in values})
    out = []
    for v in values:
        got = held.get(v["name"])
        if got is None or str(got) != str(v["value"]):
            raise Refused("not_all_prefilled", f"their '{roles.get(v['name'], {}).get('label') or v['name']}' didn't take "
                                               f"Sasha's value — no link")
        out.append({"name": v["name"], "label": v.get("label") or roles.get(v["name"], {}).get("label") or v["name"], "value": got})
    return out


def _tap(rec: dict, what: str) -> None:
    if rec["state"] in ("ready", "opened"):
        rec["taps"] += 1
        rec["tapped"].append(what)
        rec.setdefault("first_tap_at", CLOCK())


def _press(rec: dict, label: str) -> None:
    if rec["state"] in ("ready", "opened"):
        rec.update(state="pressed", pressed_label=label, _pressed=CLOCK(), pressed_at=NOW().isoformat())
        ev = rec.get("_nav")
        if ev is not None and rec.get("read_only"):
            ev.set()


def _navigated(rec: dict) -> None:
    ev = rec.get("_nav")
    if ev is not None and rec["state"] == "pressed":
        ev.set()


async def _watch(rec: dict) -> None:
    """Wait for the press (or the session's end); read their answer the moment it loads; finish; release."""
    try:
        await asyncio.wait_for(rec["_nav"].wait(), timeout=SESSION_SECONDS - 30)
    except asyncio.TimeoutError:
        await _end(rec, "expired", "no one pressed Book within 10 minutes; nothing was sent")
        return
    if rec["read_only"]:
        await _end(rec, "read_only_stopped", "the last press was made and STOPPED in the page (read-only): nothing was sent")
        return
    try:
        seen = await rec["_page"].answer()
    except Exception as e:
        seen = {"text": "", "url": None}
        log.warning("[handover] %s answer page: %s", rec["id"], e)
    await finish(rec, seen)


async def finish(rec: dict, seen: dict) -> None:
    """Their answer page → the reading (the form rung's own), the form store, the receipt, ON_BOOKED; seconds recorded."""
    from . import followup as FU
    text = " ".join((seen.get("text") or "").split())[:FR.RESPONSE_CHARS]
    reading = FU.reply_reading(text, rec.get("request") or {}) if text else {"result": "none", "why": "their answer page had no text"}
    ref = FR._REF.search(text)
    rec.update(answer_text=text, reading=reading, reference=ref.group(1) if ref else None, answered_at=NOW().isoformat(),
               press_to_answer_ms=round((CLOCK() - rec["_pressed"]) * 1000))
    if rec.get("_opened") is not None:
        rec["open_to_booked_s"] = round(CLOCK() - rec["_opened"], 1)
    booked = reading.get("result") == "confirmed"
    rec["say"] = (f"✅ Booked — {rec['venue']}" + (f", ref {rec['reference']}" if rec["reference"] else "") + ". Their page confirms it."
                  if booked else {"proposed": "Sent — their page offers something different; read it before relying on it.",
                                  "declined": "Sent — their page says no."}.get(reading.get("result"),
                                  "Sent — their page doesn't say it's confirmed; it's a request until they confirm."))
    rec["state"] = "booked" if booked else "answered"
    if rec.get("form_id") and rec.get("account_id") and FR.STORE is not None:
        trip = {"confirmed": "confirmed", "proposed": "proposed", "declined": "declined"}.get(reading.get("result"), "requested")
        try:
            await FR.STORE.finish(rec["form_id"], {"status": "sent", "sent_at": NOW(), "http_status": 200, "final_url": seen.get("url"),
                                                   "response_text": text, "response_sha256": FR._sha(text), "reading": reading,
                                                   "booking_reference": rec["reference"]},
                                  trip, "confirmed" if booked else "requested", NOW())
        except Exception as e:
            log.warning("[handover] %s store: %s", rec["id"], e)
        await _receipt(rec, reading)
    for fn in list(ON_BOOKED):
        try:
            await fn(_public(rec, ops_view=True))
        except Exception as e:
            log.warning("[handover] %s ON_BOOKED: %s", rec["id"], e)
    log.info("[handover] %s %s: press→answer %sms, taps %s, open→booked %ss", rec["id"], rec["state"], rec["press_to_answer_ms"],
             rec["taps"], rec.get("open_to_booked_s"))
    await _release(rec)


async def _receipt(rec: dict, reading: dict) -> None:
    from . import guest_receipt as GR
    o = rec.get("request") or {}
    try:
        await GR.send_for_route(rec["account_id"], rec["venue"], "their own booking form, filled by Sasha; you pressed Book",
                                {"confirmed": "Confirmed by the venue", "proposed": "They offered something else",
                                 "declined": "They said no"}.get(reading.get("result"), "Requested — not confirmed until they confirm"),
                                {"what": (o.get("what") or {}).get("activity"), "when": (o.get("when") or {}).get("at", "").replace("T", " at "),
                                 "party": (o.get("how_many") or {}).get("count"), "name": (o.get("who") or {}).get("name"),
                                 "venue_reference": rec.get("reference"), "their_words": rec.get("answer_text"), "test": rec["test"]})
    except Exception as e:
        log.warning("[handover] %s receipt: %s", rec["id"], e)


async def _end(rec: dict, state: str, why: str) -> None:
    rec.update(state=state, say=why, ended_at=NOW().isoformat())
    if state == "expired" and rec.get("form_id") and FR.STORE is not None:
        try:
            await FR.STORE.finish(rec["form_id"], {"status": "not_sent", "not_sent_why": f"live hand-over: {why}"}, "failed", "failed", NOW())
        except Exception as e:
            log.warning("[handover] %s store: %s", rec["id"], e)
    await _release(rec)


async def _release(rec: dict) -> None:
    page = rec.pop("_page", None)
    if page is not None:
        await page.close()
    if rec.get("session_id"):
        await BB.release(rec["session_id"])
    rec["live_url"] = None


def _public(rec: dict, ops_view: bool = False) -> dict:
    keep = ("id", "venue", "host", "state", "test", "read_only", "steps", "filled", "book_label", "ready_ms", "timings_ms", "fitted", "taps", "tapped",
            "press_to_answer_ms", "open_to_booked_s", "reference", "say", "reading", "created_at", "opened_at", "pressed_at",
            "answered_at", "return_to", "screenshot_sha256")
    out = {k: rec.get(k) for k in keep if k in rec}
    if ops_view:
        out.update(account_id=rec.get("account_id"), form_id=rec.get("form_id"), view_url=view_url(rec),
                   operator_url=rec.get("live_url") if rec["state"] in ("ready", "opened") else None)
    return out


def measured(rows: Optional[List[dict]] = None) -> List[dict]:
    """Per hand-over that reached their answer: the guest's taps and the seconds — for the ops log (engine_library.per_engine)."""
    return [{"engine": "own_form" if not r["test"] else "test_venue", "host": r["host"], "taps": r["taps"],
             "press_to_answer_ms": r.get("press_to_answer_ms"), "open_to_booked_s": r.get("open_to_booked_s"), "how": "measured"}
            for r in (rows if rows is not None else HANDOVERS.values()) if r["state"] in ("booked", "answered")]


# ── the routes ────────────────────────────────────────────────────────────────────────────────────────────────────

def _no(status: int, rule: str, say: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "say": say}, status_code=status)


@router.post("/forms/{form_id}/handover")
async def from_prepared_form(form_id: str, request: Request):
    """A prepared form (its read-back) → Sasha fills it in the cloud browser and the guest gets ONE link with ONE press left."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    account = account_for(request)
    f = await FR.STORE.get(account, form_id) if FR.STORE is not None else None
    if f is None:
        return _no(404, "form_unknown", "no prepared form with that id for this account")
    if f.get("status") != "awaiting_approval":
        return _no(409, "form_already", "this form was already sent or handed over")
    m = FR.form_map(f["page_url"])
    if m is None:
        return _no(422, "form_not_approved", "Sasha only hands over a form that's mapped and approved")
    if not await _robots_ok(f["page_url"]):
        return _no(422, "robots", "their robots.txt does not allow it")
    from .form_rung import _request_of
    o = await _request_of(f)
    step1 = [x for x in f["fields"] if x.get("step", 1) == 1]
    step2 = [x for x in f["fields"] if x.get("step") == 2]
    # claimed NOW: no second send (a yes, or another hand-over) can race the guest's press
    claimed = await FR.STORE.claim(account, form_id, {"how": "live_handover", "said": "the guest presses Book in the live view",
                                                      "at": NOW().isoformat(), "read_back_sha256": f["read_back_sha256"]},
                                   NOW(), NOW() - FR.APPROVAL_WINDOW)
    if claimed != "claimed":
        return _no(409 if claimed == "already" else 422, f"form_{claimed}", "this form can't be handed over now (" + claimed + ")")
    try:
        rec = await open_handover(page_url=f["page_url"], m=m, step1=step1, step2=step2, venue=_venue(f), account=account,
                                  form_id=form_id, read_only=False, return_to=(body or {}).get("return_to"), request=o)
    except Refused as e:
        await FR.STORE.finish(form_id, {"status": "not_sent", "not_sent_why": f"live hand-over refused: {e.say}"}, "failed", "failed", NOW())
        return _no(422, e.rule, e.say)
    return {"ok": True, "handover_id": rec["id"], "view_url": view_url(rec), "ready_ms": rec["ready_ms"], "taps_left": 1,
            "book_label": rec.get("book_label"), "filled": rec["filled"],
            "say": f"I've filled in {rec['venue']}'s own booking form — every field. One tap left: open it and press "
                   f"“{rec.get('book_label') or 'Book'}”. {view_url(rec)}"}


def _venue(f: dict) -> str:
    lines = f.get("read_back_lines") or []
    m = re.search(r"on (.+?)'s own", lines[0]) if lines else None
    return m.group(1) if m else (f.get("host") or "the venue")


async def _robots_ok(url: str) -> bool:
    """venue_read's robots check — its order is (http, url, resolve)."""
    from . import ladder_routes as LR
    return await V._allowed(LR.HTTP, url, LR.RESOLVE)


def _rec_for(hid: str, t: str) -> Optional[dict]:
    rec = HANDOVERS.get(hid)
    return rec if rec and t and secrets.compare_digest(rec["token"], t) and not rec["read_only"] else None


_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def summary(rec: dict) -> Dict[str, str]:
    """What the guest is booking, in their words: venue · day · time · party · name (from the reservation Sasha filled from)."""
    from datetime import date as _d
    o = rec.get("request") or {}
    at = ((o.get("when") or {}).get("at") or "")
    day = tm = ""
    if "T" in at:
        d, tm = at.split("T", 1)
        try:
            x = _d.fromisoformat(d)
            day = f"{_DAYS[x.weekday()]} {x.day} {_MONTHS[x.month - 1]}"
        except ValueError:
            day = d
    hm = o.get("how_many") or {}
    n = hm.get("count")
    party = (f"{n} {'person' if n == 1 else 'people'}" if hm.get("unit", "people") == "people" else f"{n} {hm.get('unit')}") if n else ""
    return {"venue": rec["venue"], "day": day, "time": tm[:5], "party": party, "name": (o.get("who") or {}).get("name") or ""}


@router.get("/handover/{hid}/status")
async def view_status(hid: str, t: str = ""):
    rec = _rec_for(hid, t)
    if rec is None:
        return _no(404, "handover_unknown", "this link isn't valid any more")
    return {"state": rec["state"], "say": rec.get("say"), "reference": rec.get("reference"), "return_to": rec.get("return_to")}


@router.get("/handover/{hid}/fit")
async def view_fit(hid: str, t: str = "", w: int = 390, h: int = 600):
    """The guest's frame size → the cloud browser takes it, so the live view is 1:1 and their button sits on screen."""
    rec = _rec_for(hid, t)
    if rec is None or rec["state"] not in ("ready", "opened") or rec.get("_page") is None:
        return _no(404, "handover_unknown", "this link isn't valid any more")
    w, h = max(280, min(int(w), 1024)), max(320, min(int(h), 1400))
    lock = rec.setdefault("_fit_lock", asyncio.Lock())
    async with lock:
        try:
            label = await rec["_page"].fit(w, h)
            shot = await rec["_page"].snapshot()
        except Exception as e:
            log.warning("[handover] %s fit: %s", hid, e)
            return {"ok": False}
    rec["fitted"] = [w, h]
    import base64
    return {"ok": True, "label": label or rec.get("book_label"), "snapshot": "data:image/jpeg;base64," + base64.b64encode(shot).decode()}


_LIVE_STATES = ("ready", "opened")
_ENDED = ("expired", "ended_by_operator", "read_only_stopped")


@router.get("/handover/{hid}", response_class=HTMLResponse)
async def view(hid: str, t: str = ""):
    rec = _rec_for(hid, t)
    hdr = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    if rec is None:
        return HTMLResponse(page_html(None, hid, t), 404, headers=hdr)
    if rec["state"] == "ready":
        rec.update(state="opened", _opened=CLOCK(), opened_at=NOW().isoformat())
    return HTMLResponse(page_html(rec, hid, t), headers=hdr)


def page_html(rec: Optional[dict], hid: str, t: str) -> str:
    """The guest's page — Kanoe's colours (ink, cream, gold), one screen at a time: the live form, ✅ Booked, or a calm
    'expired'. Nothing on it is a secret except the live view's own link, which only this token's holder sees."""
    if rec is None:
        state, sm, live = "gone", {"venue": "", "day": "", "time": "", "party": "", "name": ""}, ""
    else:
        state = ("live" if rec["state"] in _LIVE_STATES + ("pressed",) and rec.get("live_url") else "booked" if rec["state"] == "booked"
                 else "answered" if rec["state"] == "answered" else "expired")
        sm, live = summary(rec), (rec.get("live_url") or "")
    label = (rec or {}).get("book_label") or "Book"
    chips = "".join(f'<span class="chip">{escape(v)}</span>' for v in (
        " · ".join(x for x in (sm["day"], sm["time"]) if x), sm["party"], sm["name"]) if v)
    rep = {"@@STATE@@": state, "@@VENUE@@": escape(sm["venue"]), "@@LABEL@@": escape(label), "@@CHIPS@@": chips,
           "@@LIVE@@": escape(live, quote=True), "@@HID@@": escape(hid), "@@T@@": quote(t),
           "@@BACK@@": escape((rec or {}).get("return_to") or "", quote=True),
           "@@REF@@": escape((rec or {}).get("reference") or ""),
           "@@WHEN@@": escape(" · ".join(x for x in (sm["day"], sm["time"], sm["party"]) if x))}
    out = _VIEW
    for k, v in rep.items():
        out = out.replace(k, v)
    return out


_VIEW = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex"><title>Sasha · one tap left</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--ink:#0a0a0f;--panel:#13131b;--line:#24242f;--cream:#f0ede8;--muted:#a7a29a;--gold:#DAA520;--gold2:#E8B923;--ok:#22c55e}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--ink);color:var(--cream);
 font:15px/1.45 Inter,-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.screen{display:none;height:100dvh;flex-direction:column}.screen.on{display:flex}
.brand{display:flex;align-items:center;gap:8px;padding:10px 16px 0;font-size:13px;color:var(--muted)}
.brand b{color:var(--gold);font-weight:700;letter-spacing:.06em;text-transform:lowercase;font-size:15px}
.brand .dot{width:6px;height:6px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px rgba(34,197,94,.18)}
.card{margin:8px 12px 10px;padding:12px 14px;background:var(--panel);border:1px solid var(--line);border-radius:16px}
.card h1{margin:0;font-size:18px;font-weight:700;letter-spacing:-.01em}
.card h1 em{font-style:normal;color:var(--gold2)}
.card p{margin:2px 0 8px;color:var(--muted);font-size:14px}.card p b{color:var(--ok);font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{font-size:12.5px;padding:4px 10px;border-radius:999px;background:#1c1c26;border:1px solid var(--line)}
.frame{position:relative;flex:1;min-height:0;margin:0 12px;border-radius:14px;overflow:hidden;background:#fff;border:1px solid var(--line)}
.frame iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:#fff}
.wait{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#555;font-size:14px;background:#fff;
 pointer-events:none;transition:opacity .5s}.wait img{position:absolute;inset:0;width:100%;height:100%;object-fit:fill}
.wait .conn{position:absolute;top:8px;right:8px;font-size:11px;color:#334;background:rgba(255,255,255,.92);padding:3px 8px;
 border-radius:999px;box-shadow:0 1px 4px rgba(0,0,0,.12)}
.anim .tick{animation:pop .5s cubic-bezier(.2,1.6,.4,1)}.anim .tick path{animation:draw .5s ease-out}
.foot{padding:8px 16px calc(10px + env(safe-area-inset-bottom));font-size:12px;color:var(--muted);text-align:center}
.foot a{color:var(--muted)}
.center{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:24px}
.tick{width:84px;height:84px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 10px rgba(34,197,94,.14);display:flex;align-items:center;justify-content:center;
 margin-bottom:18px}
.tick svg{width:46px;height:46px}.tick path{stroke:var(--ink);stroke-width:6;fill:none;stroke-linecap:round;stroke-linejoin:round;
 stroke-dasharray:60;stroke-dashoffset:0}
@keyframes pop{from{transform:scale(.4);opacity:0}to{transform:scale(1);opacity:1}}@keyframes draw{from{stroke-dashoffset:60}to{stroke-dashoffset:0}}
.center h2{margin:0 0 6px;font-size:26px;font-weight:700}.center .v{font-size:17px;font-weight:600;margin:0}
.center .w{color:var(--muted);margin:4px 0 14px}.ref{font:600 14px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.04em;
 padding:8px 14px;border-radius:10px;background:var(--panel);border:1px solid var(--line);color:var(--gold2)}
.small{color:var(--muted);font-size:13px;margin-top:10px}
.btn{margin-top:22px;display:inline-block;background:var(--gold);color:#1a1405;font-weight:700;padding:13px 26px;border-radius:999px;text-decoration:none}
.soft{width:64px;height:64px;border-radius:50%;background:#1c1c26;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:16px}
</style></head><body>

<section class="screen" id="live">
 <div class="brand"><b>kanoe</b><span>·</span><span>Sasha</span><span class="dot" style="margin-left:auto"></span><span>live</span></div>
 <div class="card"><h1>Everything&#8217;s filled in at <em>@@VENUE@@</em></h1>
  <p>Just press <b>&#8220;@@LABEL@@&#8221;</b> below.</p><div class="chips">@@CHIPS@@</div></div>
 <div class="frame" id="frame"><div class="wait" id="wait">Opening their page&#8230;</div></div>
 <div class="foot">Their own website, live &#183; nothing is sent until you press &#183; <a id="full" href="@@LIVE@@">Open it full screen</a></div>
</section>

<section class="screen" id="booked">
 <div class="brand"><b>kanoe</b><span>·</span><span>Sasha</span></div>
 <div class="center"><div class="tick"><svg viewBox="0 0 52 52"><path d="M14 27l8 8 16-17"/></svg></div>
  <h2>Booked</h2><p class="v">@@VENUE@@</p><p class="w">@@WHEN@@</p>
  <div class="ref" id="ref">Ref @@REF@@</div><div class="small">Their own page confirms it.</div>
  <a class="btn" id="back" href="@@BACK@@">Back to Sasha</a><div class="small" id="close" hidden>You can close this page.</div></div>
</section>

<section class="screen" id="answered">
 <div class="brand"><b>kanoe</b><span>·</span><span>Sasha</span></div>
 <div class="center"><div class="soft">&#9993;</div><h2>Sent to @@VENUE@@</h2>
  <p class="w">Their page doesn&#8217;t confirm it yet &#8212; it&#8217;s a request until they do.<br>Sasha has their exact words.</p>
  <a class="btn" href="@@BACK@@" data-back>Back to Sasha</a></div>
</section>

<section class="screen" id="expired">
 <div class="brand"><b>kanoe</b><span>·</span><span>Sasha</span></div>
 <div class="center"><div class="soft">&#8987;</div><h2>This link has expired</h2>
  <p class="w">Nothing was sent to @@VENUE@@.<br>Ask Sasha and she&#8217;ll fill it in again in a few seconds.</p>
  <a class="btn" href="@@BACK@@" data-back>Back to Sasha</a></div>
</section>

<section class="screen" id="gone">
 <div class="brand"><b>kanoe</b><span>·</span><span>Sasha</span></div>
 <div class="center"><div class="soft">&#8987;</div><h2>This link isn&#8217;t active any more</h2>
  <p class="w">Nothing was sent. Ask Sasha for a fresh one &#8212; it takes a few seconds.</p></div>
</section>

<script>
const HID = "@@HID@@", T = "@@T@@", LIVE = document.getElementById('full').getAttribute('href'), BACK = "@@BACK@@";
function show(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.toggle('on', s.id === id));
  // the ✅ animates only where someone sees it (a background tab freezes animations at their first frame)
  const go = () => document.body.classList.add('anim');
  if (document.visibilityState === 'visible') go(); else document.addEventListener('visibilitychange', go, {once: true});
}
document.querySelectorAll('[data-back], #back').forEach(a => { if (!BACK) a.hidden = true; });
if (!BACK) document.getElementById('close').hidden = false;
let state = "@@STATE@@"; show(state);
async function start() {
  const f = document.getElementById('frame'), r = f.getBoundingClientRect();
  const w = document.getElementById('wait');
  try {
    const fit = await (await fetch(`/api/booking/handover/${HID}/fit?t=${T}&w=${Math.round(r.width)}&h=${Math.round(r.height)}`, {cache: 'no-store'})).json();
    if (fit.snapshot) { w.innerHTML = `<img alt=""><span class="conn">Connecting live&#8230;</span>`; w.querySelector('img').src = fit.snapshot; }
  } catch (e) {}
  const i = document.createElement('iframe');
  i.src = LIVE; i.title = "The venue's booking form, live"; i.setAttribute('sandbox', 'allow-same-origin allow-scripts');
  i.setAttribute('allow', 'clipboard-read; clipboard-write');
  // Browserbase's viewer paints ~10 s after it loads (measured 5 Oct): the snapshot (identical, 1:1; taps pass through it)
  // stays until the guest's tap reaches the live view (it takes focus) or 20 s after it loaded — never a blank frame
  let gone = false;
  const hide = () => { if (gone) return; gone = true; w.style.opacity = 0; setTimeout(() => w.remove(), 600); };
  window.addEventListener('blur', () => setTimeout(() => { if (document.activeElement === i) hide(); }, 0));
  i.onload = () => setTimeout(hide, 20000);
  f.insertBefore(i, w);
}
async function poll() {
  try {
    const s = await (await fetch(`/api/booking/handover/${HID}/status?t=${T}`, {cache: 'no-store'})).json();
    if (s.state === 'booked') { if (s.reference) document.getElementById('ref').textContent = 'Ref ' + s.reference; show('booked'); return; }
    if (s.state === 'answered') { show('answered'); return; }
    if (['expired', 'ended_by_operator'].includes(s.state) || s.rule === 'handover_unknown') { show(s.rule ? 'gone' : 'expired'); return; }
  } catch (e) {}
  setTimeout(poll, 600);
}
if (state === 'live') { start(); poll(); }
</script></body></html>"""


# ── ops (founder only): the console's list, the operator's takeover, the rehearsal ───────────────────────────────

@ops.get("/handovers")
async def ops_list(request: Request):
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    rows = sorted(HANDOVERS.values(), key=lambda r: r["created_at"], reverse=True)
    from . import engine_library as EL
    return {"ok": True, "cloud_browser": status(), "handovers": [_public(r, ops_view=True) for r in rows[:50]],
            "per_engine": EL.per_engine(measured(rows))}


@ops.post("/handovers/{hid}/end")
async def ops_end(hid: str, request: Request):
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    rec = HANDOVERS.get(hid)
    if rec is None:
        return _no(404, "handover_unknown", "no such hand-over")
    if rec.get("_watch"):
        rec["_watch"].cancel()
    await _end(rec, "ended_by_operator", "ended from the ops console; nothing was sent")
    return {"ok": True, "state": rec["state"]}


#: a fictional guest — never a real person's details through the cloud browser before a DPA
FICTIONAL = {"person_name": "Prueba Sasha", "email": "prueba@example.com", "phone": "+34600000000", "party_size": "2",
             "free_text": "Prueba de Kanoe (ficticia)."}


@ops.post("/handovers/rehearse")
async def ops_rehearse(request: Request):
    """{"variant": "plain"|"wizard"|"consent"|"captcha"} → our test venue, a fictional guest, the guest's link (the founder or
    the rehearsal presses). {"url": "<an approved venue's own form>", "read_only": true, "date": "YYYY-MM-DD", "time": "HH:MM"}
    → filled up to the last press in a session where nothing can be sent; the screenshot's hash and the fields come back."""
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body or {}
    url = body.get("url") or FR.test_venue_url(body.get("variant") or "plain")
    m = FR.form_map(url) if FR.is_test_venue(url) else (FR.FORM_MAPS.get((urlsplit(url).hostname or "").lower()) and
                                                        {**FR.FORM_MAPS[(urlsplit(url).hostname or "").lower()], "test": False})
    if not m:
        return _no(422, "form_not_mapped", "only our test venue or a mapped venue's own form (form_rung.FORM_MAPS)")
    read_only = bool(body.get("read_only")) or not m.get("test")      # a real venue is ALWAYS read-only here
    if not await _robots_ok(url):
        return _no(422, "robots", "their robots.txt does not allow it")
    from datetime import date as _d, time as _t
    vals = {**FICTIONAL, "date": m["date_fmt"](_d.fromisoformat(body.get("date") or "2026-12-15")),
            "time": m["time_fmt"](_t.fromisoformat(body.get("time") or "21:00"))}
    if m.get("phone_fmt"):
        vals["phone"] = m["phone_fmt"](vals["phone"])
    one = {"date", "time", "party_size"}
    wizard = FR.is_test_venue(url) and url.rstrip("/").endswith("/wizard")
    step1 = [{"name": n, "value": vals[r], "label": lbl} for n, (r, lbl) in m["fields"].items()
             if r in vals and (not wizard or r in one)]
    step2 = [{"name": n, "value": vals[r], "label": lbl} for n, (r, lbl) in m["fields"].items() if wizard and r in vals and r not in one]
    step1 += [{"name": n, "value": v, "label": lbl} for n, (v, lbl) in (m.get("fixed") or {}).items()]
    o = {"what": {"activity": "table", "activity_venue_lang": "mesa", "category": "restaurant"},
         "when": {"mode": "at", "at": f"{body.get('date') or '2026-12-15'}T{body.get('time') or '21:00'}"},
         "how_many": {"count": 2, "unit": "people"}, "who": {"name": FICTIONAL["person_name"]}}
    try:
        rec = await open_handover(page_url=url, m=m, step1=step1, step2=step2, venue="Sasha Test Venue" if m.get("test") else urlsplit(url).hostname,
                                  account=None, form_id=None, read_only=read_only, return_to=body.get("return_to"), request=o, fictional=True)
    except Refused as e:
        return _no(422, e.rule, e.say)
    out = {"ok": True, **_public(rec, ops_view=True)}
    if read_only:
        import base64
        out["screenshot_png_b64"] = base64.b64encode(rec.get("_screenshot") or b"").decode()
        out["operator_url_read_only"] = rec.get("live_url")   # to LOOK; any press is cancelled in the page and blocked on the wire
    return out


__all__ = ["router", "ops", "open_handover", "check_page", "still_empty", "finish", "measured", "status", "ON_BOOKED", "HANDOVERS", "Refused"]
