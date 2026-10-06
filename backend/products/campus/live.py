"""CR 33 · CampusMe's LIVE hand-over: the school's own visit-registration form (Slate), filled in Kanoe's cloud browser from the
student's details (the Keep, or what the parent said), the session chosen IN the form — and stopped before the last press.

Two taps are left for the parent, on their phone (the same guest page as every hand-over):
  ① the school's statement box ("By submitting this form, you understand…") — a statement is theirs; CampusMe never ticks one;
  ② the school's own SUBMIT. Pressing it registers the student with the school; not pressing sends nothing.
Rules (each a refusal, never a guess):
  · only a real guest under the founder override (or the signed DPA) — HO.dpa_ok; rehearsals are READ-ONLY with a fictional student;
  · one-page Slate forms only (Penn): a form that needs a "next page" press first is refused, never advanced;
  · a CAPTCHA, a platform's frame or a payment field on the page → no link;
  · every required visible question filled and read back, or no link; the SMS opt-in and every optional extra left alone;
  · read-only: every non-GET request is aborted in the cloud browser and the press is cancelled in the page.
Penn's form read 6 Oct 2026 (key.admissions.upenn.edu/portal/campus-visit, robots allow): SUBMIT is a script button
(button.form_button_submit) that posts by XHR (cmd=submit&output=xdm) — so the press is watched on the button itself.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from booking_signer import handover as HO

from . import schools as SC
from .slate import Session

log = logging.getLogger("products.campus.live")
SUBMIT = "button.form_button_submit"
BOX = '.form_question[data-export="understand"] input[type=checkbox]'
BOX_WORDS = "Tick “Yes, I understand”"
NEEDS = ("first", "last", "email", "birthdate", "grad_year")
_CHALLENGE = re.compile(r"recaptcha|hcaptcha|turnstile|cf-chl", re.I)
_DONE = re.compile(r"thank you|registration (is )?(complete|confirmed|received)|you('| a)re registered|has been (received|submitted)|"
                   r"confirmation", re.I)
FICTIONAL = {"first": "Prueba", "last": "Sasha", "email": "prueba@example.com", "birthdate": "2009-03-14",
             "high_school": "Kanoe Test High School", "grad_year": "2027"}


def _q(export: str) -> str:
    return f'.form_question[data-export="{export}"]'


_READ_SLATE_JS = """() => {
  const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length)) && getComputedStyle(e).visibility !== 'hidden';
  const qs = [...document.querySelectorAll('.form_question')].filter(q => !['header','h2','p','hidden'].includes(q.dataset.type)).map(q => {
    const ins = [...q.querySelectorAll('input:not([type=hidden]), select, textarea')];
    const sel = ins.filter(i => i.tagName === 'SELECT');
    const ticked = ins.filter(i => (i.type === 'checkbox' || i.type === 'radio') && i.checked);
    const text = ins.filter(i => i.tagName !== 'SELECT' && i.type !== 'checkbox' && i.type !== 'radio');
    const value = ticked.length ? ticked.map(i => i.value).join('|')
      : sel.length ? sel.map(s => s.selectedIndex > 0 ? s.options[s.selectedIndex].text : '').join(' ').trim()
      : text.map(i => i.value).join(' ').trim();
    return {export: q.dataset.export || '', type: q.dataset.type, required: q.dataset.required === '1', visible: vis(q),
            label: (q.querySelector('.form_label')?.innerText || '').trim().slice(0, 80), value,
            options: sel.length === 1 ? [...sel[0].options].map(o => o.text.trim()).filter(Boolean) : []};
  });
  const pay = [...document.querySelectorAll('input')].some(i => (i.autocomplete || '').startsWith('cc-'));
  const submit = document.querySelector('button.form_button_submit');
  return {url: location.href, qs, frames: [...document.querySelectorAll('iframe')].map(f => f.src || ''), pay,
          pages: Number((document.querySelector('[data-page-count]') || {dataset: {}}).dataset.pageCount || 1),
          next: [...document.querySelectorAll('button.form_button_next, .form_page_next, button.form_button_continue')].some(vis),
          submit: submit && vis(submit) ? submit.innerText.trim() : '', captcha: /recaptcha|hcaptcha|turnstile|cf-chl/i.test(document.documentElement.outerHTML),
          text: (document.body && document.body.innerText || '').slice(0, 4000)};
}"""

_WATCH_SLATE_JS = """() => {
  if (window.__kanoeWatching) return; window.__kanoeWatching = true;
  document.addEventListener('pointerdown', e => { try { window.__kanoeTap((e.target && (e.target.innerText || e.target.name || e.target.tagName) || '').slice(0, 40)); } catch (_) {} }, true);
  document.addEventListener('click', e => {
    const b = e.target && e.target.closest && e.target.closest('button.form_button_submit');
    if (!b) return;
    if (window.__kanoeReadOnly) { e.preventDefault(); e.stopImmediatePropagation(); }
    try { window.__kanoePress((b.innerText || '').trim()); } catch (_) {}
  }, true);
}"""


class SlatePage(HO.PlaywrightPage):
    """The school's Slate form: it reads, selects, types, ticks the chosen session, and points — it decides nothing."""

    async def guard(self, read_only: bool) -> None:
        async def gate(route):
            r = route.request
            if HO._PAY_FRAME.search(r.url) or (read_only and r.method not in ("GET", "HEAD", "OPTIONS")):
                await route.abort()
            else:
                await route.continue_()
        await self.page.route("**/*", gate)
        if read_only:
            await self.page.add_init_script("window.__kanoeReadOnly = true")

    async def settle(self) -> None:
        await self.page.wait_for_selector(f'{_q("RegistrantType")} select, {_q("sys:first")} input', state="attached", timeout=20000)

    async def read_slate(self) -> dict:
        return await self.page.evaluate(_READ_SLATE_JS)

    async def choose(self, export: str, want: str) -> str:
        """A select, by its option's words (exact first, then contained); the page's own change event fires."""
        loc = self.page.locator(f"{_q(export)} select").first
        await loc.wait_for(state="visible", timeout=8000)
        opts = [o.strip() for o in await loc.locator("option").all_inner_texts()]
        pick = next((o for o in opts if o.lower() == want.lower()), None) or next((o for o in opts if want.lower() in o.lower()), None)
        if not pick:
            raise HO.Refused("not_all_prefilled", f"their “{export}” has no option “{want}” — no link")
        await loc.select_option(label=pick)
        return pick

    async def type_in(self, export: str, value: str) -> None:
        loc = self.page.locator(f"{_q(export)} input").first
        await loc.wait_for(state="visible", timeout=8000)
        await loc.fill(value)
        await self.page.keyboard.press("Escape")          # closes a suggestion list (the school-name lookup)

    async def birthdate(self, iso: str) -> None:
        y, m, d = iso.split("-")
        q = _q("sys:birthdate")
        for part, v in (("_m", m), ("_d", d), ("_y", y)):
            loc = self.page.locator(f'{q} select[name$="{part}"]').first
            await loc.wait_for(state="visible", timeout=8000)
            await loc.select_option(value=v)

    async def tick_session(self, event_id: str) -> None:
        loc = self.page.locator(f'input[type=checkbox][value^="id={event_id}&"]').first
        await loc.wait_for(state="attached", timeout=8000)
        await loc.check(force=True)

    async def point_at_book(self) -> str:
        return await self.page.evaluate(HO._POINT_BOX_JS, [SUBMIT, BOX, BOX_WORDS])

    async def watch(self, on_tap, on_press, read_only: bool, on_navigated) -> None:
        await self.page.expose_function("__kanoeTap", on_tap)
        await self.page.expose_function("__kanoePress", on_press)
        if read_only:
            await self.page.evaluate("window.__kanoeReadOnly = true")
        await self.page.add_init_script(f"({_WATCH_SLATE_JS})()")
        await self.page.evaluate(_WATCH_SLATE_JS)

    async def answer(self) -> dict:
        """After SUBMIT: the school's own reply, drawn in the page (no navigation) — until it changes, at most 20 s."""
        try:
            await self.page.wait_for_function("""() => { const b = document.querySelector('button.form_button_submit');
                return !b || !(b.offsetWidth || b.offsetHeight) || /thank you|confirm|registered|error|required/i.test(document.body.innerText); }""",
                                              timeout=20000)
        except Exception:
            pass
        return await self.read_slate()


PAGE_FACTORY = SlatePage


def missing(profile: Dict[str, str]) -> List[str]:
    return [k for k in NEEDS if not (profile.get(k) or "").strip()]


def values(profile: Dict[str, str], session: Session, attendees: int) -> List[dict]:
    """What goes in, in the form's order, each with its source — the same answers the CR 1 hand-over page lists."""
    p = profile
    v = [("RegistrantType", "select", "Prospective Student/Parent", "you're registering a prospective student"),
         ("sys:attendees", "select", str(attendees), f"the student and {attendees - 1} guest{'s' if attendees != 2 else ''}"),
         ("sys:field:prospect_type", "select", "First-year", "a high-school student applies as a first-year"),
         ("sys:field:term", "select", f"Fall {p['grad_year']}", f"graduating {p['grad_year']}"),
         ("session", "session", session.event_id or "", "the session you picked"),
         ("sys:first", "text", p["first"], "the student's details"), ("sys:last", "text", p["last"], "the student's details"),
         ("sys:email", "text", p["email"], "the student's details"), ("sys:email2", "text", p["email"], "the same email, confirmed"),
         ("sys:birthdate", "date", p["birthdate"], "the student's details")]
    if p.get("high_school"):
        v.append(("schoolname", "text", p["high_school"], "the student's details"))
    if p.get("mobile"):
        v.append(("sys:mobile", "text", p["mobile"], "the student's details"))
    return [{"export": e, "kind": k, "value": val, "source": s} for e, k, val, s in v]


def check(seen: dict) -> List[str]:
    """Required visible questions still empty (the statement box excepted) — any one means no link."""
    return [q["label"] or q["export"] for q in seen["qs"]
            if q["required"] and q["visible"] and not q["value"] and q["export"] != "understand"]


def _when(session: Session) -> Dict[str, str]:
    d = date.fromisoformat(session.day)
    return {"day": f"{HO._DAYS[d.weekday()]} {d.day} {HO._MONTHS[d.month - 1]}", "time": session.start}


async def open_campus_handover(*, session: Session, profile: Dict[str, str], attendees: int, account: Optional[str],
                               read_only: bool, fictional: bool, return_to: Optional[str] = None) -> dict:
    s = SC.SCHOOLS[session.school]
    if not HO.configured():
        raise HO.Refused("cloud_browser_not_configured", "the live hand-over isn't set up on this server (BROWSERBASE_API_KEY)")
    if not read_only and not fictional and not HO.dpa_ok(account):
        raise HO.Refused("no_dpa", "a real student's details don't go through the cloud browser until Kanoe has a signed "
                                   "data-processing agreement with it")
    if s.get("variant") != "register" or not session.event_id:
        raise HO.Refused("two_pages", f"{s['name']}'s form needs a page turned before its last button — the live hand-over only "
                                      "takes one-page forms; the question-by-question page is the way there")
    gone = missing(profile)
    if gone:
        raise HO.Refused("missing_info", "CampusMe needs these first: " + ", ".join(gone).replace("_", " "))
    if HO.V.platform_of(session.form_url):
        raise HO.Refused("platform", "that registration page is a platform's, not the school's")
    vals = values(profile, session, attendees)
    title = session.title.split(" · ")[0]
    t0 = HO.CLOCK()
    hid = uuid.uuid4().hex[:12]
    rec: Dict[str, Any] = {"id": hid, "token": HO._token(), "account_id": account, "form_id": None, "venue": f"{s['name']} — {title}",
                           "page_url": session.form_url, "host": urlsplit(session.form_url).hostname, "read_only": read_only,
                           "test": False, "state": "filling", "created_at": HO.NOW().isoformat(), "taps": 0, "tapped": [],
                           "return_to": HO._return_ok(return_to), "request": None, "steps": 1, "engine": "Slate", "taps_left": 2,
                           "press_is_final": True, "box_label": "Yes, I understand", "fictional": fictional, "campus": True,
                           "summary": {"venue": f"{s['name']} — {title}", **_when(session),
                                       "party": f"{attendees} attendee{'s' if attendees != 1 else ''}",
                                       "name": f"{profile['first']} {profile['last']}"},
                           "fallback_link": session.form_url}
    lap = HO._laps(rec, t0)
    sess = await HO.BB.create(f"campus-handover:{hid}")
    lap("session")
    rec["session_id"] = sess["id"]
    page = PAGE_FACTORY()
    try:
        await page.connect(sess["connectUrl"])
        await page.guard(read_only)
        lap("connect")
        await page.goto(session.form_url)
        await page.settle()
        lap("page")
        seen = await page.read_slate()
        if seen["captcha"]:
            raise HO.Refused("captcha", f"{s['name']}'s form has a CAPTCHA — Sasha never solves one, so no link; the school's own page: "
                                        f"{session.form_url}")
        if any(HO.V.platform_of(f) or HO._PAY_FRAME.search(f) for f in seen["frames"] if f) or seen["pay"]:
            raise HO.Refused("payment_step", "the page carries a platform's or a payment frame — never through Kanoe's browser")
        if seen["next"] or seen["pages"] > 1:
            raise HO.Refused("two_pages", f"{s['name']}'s form has more than one page — no link")
        filled = []
        for v in vals:
            if v["kind"] == "select":
                got = await page.choose(v["export"], v["value"])
            elif v["kind"] == "session":
                await page.tick_session(v["value"])
                got = title
            elif v["kind"] == "date":
                await page.birthdate(v["value"])
                got = v["value"]
            else:
                await page.type_in(v["export"], v["value"])
                got = v["value"]
            filled.append({"name": v["export"], "label": v["export"], "value": got, "source": v["source"]})
        lap("fill")
        seen = await page.read_slate()
        by = {q["export"]: q for q in seen["qs"] if q["export"]}
        for v in vals:                                  # each value read back from the page
            if v["kind"] in ("text",) and by.get(v["export"], {}).get("value") != v["value"]:
                raise HO.Refused("not_all_prefilled", f"their “{v['export']}” didn't keep Sasha's value — no link")
            if v["kind"] == "session" and not any(f"id={v['value']}&" in (q["value"] or "") for q in seen["qs"]):
                raise HO.Refused("not_all_prefilled", "the session didn't stay chosen in their form — no link")
        empty = check(seen)
        if empty:
            raise HO.Refused("not_all_prefilled", f"their form still needs: {', '.join(empty)} — no link")
        if by.get("understand", {}).get("value"):
            raise HO.Refused("consent_box", "the statement box is ticked — only the parent may tick it; no link")
        if by.get("sys:field:text_opt_in", {}).get("value"):
            raise HO.Refused("consent_box", "the SMS opt-in has an answer — that's the parent's alone; no link")
        if seen["captcha"]:
            raise HO.Refused("captcha", "a CAPTCHA appeared while filling — no link")
        rec["filled"] = filled
        rec["book_label"] = await page.point_at_book()
        if not rec["book_label"]:
            raise HO.Refused("unexpected_step", "the statement box or SUBMIT isn't where it should be — no link")
        rec["_nav"] = asyncio.Event()
        _, live = await asyncio.gather(
            page.watch(lambda what: HO._tap(rec, what), lambda label: HO._press(rec, label), read_only, lambda: None),
            HO.BB.live_urls(sess["id"]))
        lap("live_view")
        fs = (live.get("pages") or [{}])[0].get("debuggerFullscreenUrl") or live.get("debuggerFullscreenUrl")
        rec.update(live_url=f"{fs}&navbar=false" if "?" in (fs or "") else fs, state="ready",
                   ready_ms=round((HO.CLOCK() - t0) * 1000), ready_at=HO.NOW().isoformat())
        if read_only:
            rec["_screenshot"] = await page.screenshot()
    except HO.Refused:
        await page.close()
        await HO.BB.release(sess["id"])
        raise
    except Exception as e:
        await page.close()
        await HO.BB.release(sess["id"])
        log.warning("[campus-handover] %s failed: %s: %s", hid, type(e).__name__, e)
        raise HO.Refused("handover_failed", f"the cloud browser couldn't prepare {s['name']}'s form ({type(e).__name__}) — no link") from None
    rec["_page"] = page
    rec["_watch"] = asyncio.ensure_future(_watch(rec))
    HO.HANDOVERS[hid] = rec
    log.info("[campus-handover] %s ready in %sms: %s (read_only=%s)", hid, rec["ready_ms"], rec["venue"], read_only)
    return rec


async def _watch(rec: dict) -> None:
    try:
        await asyncio.wait_for(rec["_nav"].wait(), timeout=HO.SESSION_SECONDS - 30)
    except asyncio.TimeoutError:
        await HO._end(rec, "expired", "no one pressed SUBMIT within 10 minutes; nothing was sent to the school")
        return
    if rec["read_only"]:
        await HO._end(rec, "read_only_stopped", "SUBMIT was pressed and STOPPED in the page (read-only): nothing was sent")
        return
    try:
        seen = await rec["_page"].answer()
    except Exception as e:
        seen = {"text": "", "qs": []}
        log.warning("[campus-handover] %s answer: %s", rec["id"], e)
    await finish(rec, seen)


async def finish(rec: dict, seen: dict) -> None:
    """The school's reply as its page shows it, in its words; ✅ only when the page says so."""
    rec["press_to_answer_ms"] = round((HO.CLOCK() - rec["_pressed"]) * 1000)
    if rec.get("_opened") is not None:
        rec["open_to_booked_s"] = round(HO.CLOCK() - rec["_opened"], 1)
    text = " ".join((seen.get("text") or "").split())[:4000]
    m = _DONE.search(text)
    done = bool(m) and not seen.get("submit")
    rec.update(answer_text=text, answered_at=HO.NOW().isoformat(), state="booked" if done else "answered",
               say=(f"✅ Registered — {rec['venue']}. The school's page says: “{text[max(0, m.start() - 20):m.start() + 140].strip()}”"
                    if done else "Pressed — the school's page doesn't say the registration went through; check the email they send."))
    for fn in list(CAMPUS_DONE):
        try:
            await fn(HO._public(rec, ops_view=True))
        except Exception as e:
            log.warning("[campus-handover] %s done hook: %s", rec["id"], e)
    await HO._release(rec)


CAMPUS_DONE: List[Any] = []        # turn.py records the outcome on the campus case
