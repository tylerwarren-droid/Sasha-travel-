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
        import httpx
        key = os.getenv("BROWSERBASE_API_KEY", "").strip()
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
            r = await c.request(method, f"{API}{path}", json=json, headers={"X-BB-API-Key": key})
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
        """The form's own Book button, scrolled into view and outlined — one round trip; its words come back."""
        return await self.page.evaluate("""(sel) => {
          const form = [...document.forms].find(f => f.querySelectorAll('input:not([type=hidden]), select, textarea').length >= 3);
          const bs = form ? form.querySelectorAll(sel) : []; const b = bs[bs.length - 1];
          if (!b) return '';
          b.scrollIntoView({block: 'center'}); b.style.outline = '3px solid #22c55e'; b.style.outlineOffset = '3px';
          return (b.tagName === 'BUTTON' ? b.innerText : b.value || '').trim();
        }""", _SUBMIT)

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
    keep = ("id", "venue", "host", "state", "test", "read_only", "steps", "filled", "book_label", "ready_ms", "timings_ms", "taps", "tapped",
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
    if not await V._allowed(*_http(), f["page_url"]):
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


def _http():
    from . import ladder_routes as LR
    return LR.HTTP, LR.RESOLVE


def _rec_for(hid: str, t: str) -> Optional[dict]:
    rec = HANDOVERS.get(hid)
    return rec if rec and t and secrets.compare_digest(rec["token"], t) and not rec["read_only"] else None


@router.get("/handover/{hid}/status")
async def view_status(hid: str, t: str = ""):
    rec = _rec_for(hid, t)
    if rec is None:
        return _no(404, "handover_unknown", "this link isn't valid any more")
    return {"state": rec["state"], "say": rec.get("say"), "reference": rec.get("reference"), "return_to": rec.get("return_to")}


@router.get("/handover/{hid}", response_class=HTMLResponse)
async def view(hid: str, t: str = ""):
    rec = _rec_for(hid, t)
    if rec is None:
        return HTMLResponse("<p style='font:16px system-ui;padding:24px'>This link isn't valid any more. Ask Sasha for a new one.</p>", 404)
    if rec["state"] == "ready":
        rec.update(state="opened", _opened=CLOCK(), opened_at=NOW().isoformat())
    live = rec.get("live_url") if rec["state"] in ("opened", "ready") else None
    return HTMLResponse(_VIEW.format(venue=escape(rec["venue"]), label=escape(rec.get("book_label") or "Book"),
                                     live=escape(live or "about:blank", quote=True), hid=escape(hid), t=quote(t),
                                     back=escape(rec.get("return_to") or "", quote=True)),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


_VIEW = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sasha — one tap left</title><style>
:root{{--bg:#0b0f14;--fg:#f4f6f8;--muted:#9aa4af;--ok:#22c55e}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,-apple-system,sans-serif;height:100dvh;display:flex;flex-direction:column}}
header{{padding:10px 16px;border-bottom:1px solid #1f2933}} header b{{color:var(--ok)}} header small{{color:var(--muted);display:block}}
iframe{{flex:1;border:0;width:100%;background:#fff}}
#done{{display:none;position:fixed;inset:0;background:var(--bg);align-items:center;justify-content:center;flex-direction:column;text-align:center;padding:24px}}
#done h1{{font-size:28px;margin:0 0 8px}} #done a{{margin-top:18px;background:var(--ok);color:#06210f;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600}}
</style></head><body>
<header>Sasha filled in <b>{venue}</b>'s own form — every field. Check it, then press <b>“{label}”</b>.
<small>Their website, live. Nothing is sent until you press. Kanoe never sees a card here.</small></header>
<iframe src="{live}" sandbox="allow-same-origin allow-scripts" allow="clipboard-read; clipboard-write" title="{venue}'s booking form"></iframe>
<div id="done"><h1 id="say"></h1><p id="ref"></p><a id="back" href="{back}">Back to Sasha</a></div>
<script>
const back = "{back}"; let shown = false;
async function poll() {{
  try {{
    const r = await fetch("/api/booking/handover/{hid}/status?t={t}", {{cache: "no-store"}}); const s = await r.json();
    if (["booked","answered","expired"].includes(s.state) && !shown) {{
      shown = true; document.getElementById("say").textContent = s.say || "";
      document.getElementById("done").style.display = "flex";
      if (!back) document.getElementById("back").style.display = "none";
      else if (s.state === "booked") setTimeout(() => location.href = back, 2500);
      return;
    }}
  }} catch (e) {{}}
  setTimeout(poll, 700);
}}
poll();
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
    if not await V._allowed(*_http(), url):
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
