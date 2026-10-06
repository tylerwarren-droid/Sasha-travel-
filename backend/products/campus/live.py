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
import urllib.parse
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
            await fn({**HO._public(rec, ops_view=True), "answer_text": text})   # CR 45 · its words, for the confirmation check
        except Exception as e:
            log.warning("[campus-handover] %s done hook: %s", rec["id"], e)
    await HO._release(rec)


CAMPUS_DONE: List[Any] = []        # turn.py records the outcome on the campus case


# ── CR 38 · the four-school tour: Yale and Brown's own Slate forms, filled for the family's press ────────────────────
# Read in the cloud browser, read-only, 6 Oct 2026 (nothing typed, every write aborted):
#   · Yale: "I am a visiting:" (Prospective Student / Educator) reveals the student's questions on the same screen; a
#     "Continue" button (2 pages) — pressed with nothing filled it sent NOTHING (only the page's own seat-count read);
#   · Brown: "Select the option which best describes you." (Prospective Student / Parent… / Counselor) reveals its pages;
#     its Submit is on screen from the start; the session is chosen by its own link (/register/?id=…).
# Left for the family, always: Brown's "Do you have time to answer additional questions?", its accommodations question,
# its mobile box (it carries a consent to texts), and every school's last press.

TOUR_FIRST = {"yale": "Prospective Student", "brown": "Prospective Student"}


def tour_values(school: str, fam: Dict[str, str]) -> List[dict]:
    """What goes in each school's form (by Slate's own export names), from the family's details (the Keep)."""
    f = fam
    first, last = (f.get("student_first") or ""), (f.get("student_last") or "")
    party = max(1, min(int(f.get("party") or 1), 4))
    v = []
    if school == "yale":
        v += [("sys:email", "text", f.get("email")), ("sys:first", "text", first), ("sys:last", "text", last),
              ("sys:birthdate", "date", f.get("birthdate")), ("sys:address", "address", f.get("address")),
              ("sys:mobile", "text", f.get("mobile")), ("sys:field:term", "select", f"Fall {f.get('grad_year')}" if f.get("grad_year") else None),
              ("sys:field:type", "select", "First-Year"), ("sys:school:name", "text", f.get("high_school")),
              ("sys:guests", "select", str(min(3, party - 1))), ("sys:field:parent1_email", "text", f.get("parent_email"))]
    elif school == "brown":
        v += [("sys:first", "text", first), ("sys:last", "text", last), ("sys:preferred", "text", first),
              ("sys:email", "text", f.get("email")), ("sys:field:student_type", "select", "First-Year/Freshman"),
              ("sys:field:term", "select", f"Fall {f.get('grad_year')}" if f.get("grad_year") else None),
              ("sys:school:name", "text", f.get("high_school")), ("sys:birthdate", "date", f.get("birthdate")),
              ("sys:attendees", "select", str(min(3, party)))]
    return [{"export": e, "kind": k, "value": x} for e, k, x in v if x]


_ADDR = re.compile(r"^\s*(?P<street>[^,]+),\s*(?P<city>[^,]+),\s*(?P<region>[A-Za-z .]+?)\s+(?P<postal>\d{5}(?:-\d{4})?)\s*(?:,\s*(?P<country>.+))?$")


class SlateTourPage(SlatePage):
    async def first_answer(self, answer: str) -> None:
        await self.page.wait_for_load_state("load", timeout=20000)
        loc = self.page.locator(f'.form_question input[type=radio][value="{answer}"]').first
        await loc.wait_for(state="visible", timeout=15000)
        await loc.check(force=True)
        await self.page.wait_for_timeout(800)

    async def fill_q(self, export: str, kind: str, value: str) -> str:
        q = self.page.locator(f'{_q(export)}:visible').first
        await q.wait_for(state="visible", timeout=8000)
        if kind == "text":
            inp = q.locator("input:not([type=hidden]), textarea").first
            await inp.fill(value)
            await self.page.keyboard.press("Escape")
            return await inp.input_value()
        if kind == "select":
            sel = q.locator("select").first
            opts = [o.strip() for o in await sel.locator("option").all_inner_texts()]
            pick = next((o for o in opts if o.lower() == value.lower()), None)
            if not pick:
                raise HO.Refused("not_all_prefilled", f"their “{export}” has no option “{value}” — no link")
            await sel.select_option(label=pick)
            return pick
        if kind == "date":
            y, m, d = value.split("-")
            for part, val in (("_m", m), ("_d", d), ("_y", y)):
                await q.locator(f'select[name$="{part}"]').first.select_option(value=val)
            return value
        if kind == "address":
            a = _ADDR.match(value or "")
            if not a:
                raise HO.Refused("not_all_prefilled", "the mailing address isn't in the shape the form needs (street, city, state ZIP)")
            await q.locator('select[name$="_country"]').first.select_option(label="United States")
            await self.page.wait_for_timeout(400)
            await q.locator('textarea[name$="_street"], input[name$="_street"]').first.fill(a["street"].strip())
            await q.locator('input[name$="_city"]').first.fill(a["city"].strip())
            reg = q.locator('select[name$="_region"]').first
            region = a["region"].strip()
            try:
                await reg.select_option(value=region.upper()) if len(region) == 2 else await reg.select_option(label=region)
            except Exception:
                raise HO.Refused("not_all_prefilled", f"their state list has no “{region}” — no link")
            await q.locator('input[name$="_postal"]').first.fill(a["postal"])
            return value
        raise ValueError(kind)

    async def tick_time(self, start_hhmm: str) -> bool:
        """Yale's tour times are ticked in its form (its own words: "pick the tour time(s)"): the box whose summary says that time."""
        h, mi = map(int, start_hhmm.split(":"))
        words = f"{(h % 12) or 12}:{mi:02d} {'AM' if h < 12 else 'PM'}"
        boxes = self.page.locator('input[type=checkbox][data-event], input[type=checkbox][name$="_event"]')
        for i in range(await boxes.count()):
            b = boxes.nth(i)
            val = urllib.parse.unquote(await b.get_attribute("value") or "")     # "Monday%2c … 9%3a00 AM": encoded
            if words in val and await b.is_visible():
                await b.check(force=True)
                return True
        return False

    async def press_continue(self) -> bool:
        btn = self.page.locator("button:visible", has_text="Continue")
        if not await btn.count():
            return False
        await btn.first.click()
        await self.page.wait_for_timeout(2500)
        return True


TOUR_FACTORY = SlateTourPage


FAMILY_BOXES = {"brown": ('.form_question[data-export="additional_questions_student"] input[type=radio]',
                          "Answer “additional questions?”")}
NOT_OURS = {"additional_questions_student", "sys:mobile", "accommodationperson", "ada_details"}


async def open_tour_handover(*, school: str, session: Session, fam: Dict[str, str], account: Optional[str], read_only: bool,
                             fictional: bool) -> dict:
    """CR 38 · Yale's or Brown's own form, filled in Kanoe's cloud browser for the family's press (founder override until the
    DPA). Everything is read back from the page; what is the family's stays theirs; SUBMIT is never pressed."""
    s = SC.SCHOOLS[school]
    if not HO.configured():
        raise HO.Refused("cloud_browser_not_configured", "the live hand-over isn't set up on this server (BROWSERBASE_API_KEY)")
    if not read_only and not fictional and not HO.dpa_ok(account):
        raise HO.Refused("no_dpa", "a real family's details don't go through the cloud browser until Kanoe has a signed "
                                   "data-processing agreement with it")
    if school not in TOUR_FIRST:
        raise HO.Refused("not_supported", f"{s['name']}'s form isn't one the live hand-over fills")
    vals = tour_values(school, fam)
    title = session.title.split(" · ")[0]
    t0 = HO.CLOCK()
    hid = uuid.uuid4().hex[:12]
    rec: Dict[str, Any] = {"id": hid, "token": HO._token(), "account_id": account, "form_id": None, "venue": f"{s['name']} — {title}",
                           "page_url": session.form_url, "host": urlsplit(session.form_url).hostname, "read_only": read_only,
                           "test": False, "state": "filling", "created_at": HO.NOW().isoformat(), "taps": 0, "tapped": [],
                           "return_to": None, "request": None, "steps": 1, "engine": "Slate", "press_is_final": True,
                           "taps_left": 2 if school in FAMILY_BOXES else 1, "fictional": fictional, "campus": True,
                           "box_label": FAMILY_BOXES.get(school, (None, None))[1],
                           "summary": {"venue": f"{s['name']} — {title}", **_when(session),
                                       "party": f"{fam.get('party') or 1} visitor{'s' if str(fam.get('party') or 1) != '1' else ''}",
                                       "name": f"{fam.get('student_first', '')} {fam.get('student_last', '')}".strip()},
                           "fallback_link": session.form_url}
    lap = HO._laps(rec, t0)
    sess = await HO.BB.create(f"campus-tour:{hid}")
    lap("session")
    rec["session_id"] = sess["id"]
    page = TOUR_FACTORY()
    try:
        await page.connect(sess["connectUrl"])
        await page.guard(read_only)
        lap("connect")
        await page.goto(session.form_url)
        await page.first_answer(TOUR_FIRST[school])
        lap("page")
        seen = await page.read_slate()
        if seen["captcha"]:
            raise HO.Refused("captcha", f"{s['name']}'s form has a CAPTCHA — Sasha never solves one; its own page: {session.form_url}")
        if any(HO.V.platform_of(f) or HO._PAY_FRAME.search(f) for f in seen["frames"] if f) or seen["pay"]:
            raise HO.Refused("payment_step", "the page carries a platform's or a payment frame — never through Kanoe's browser")
        filled = []
        for v in vals:
            got = await page.fill_q(v["export"], v["kind"], v["value"])
            if v["kind"] == "text" and got != v["value"]:
                raise HO.Refused("not_all_prefilled", f"their “{v['export']}” didn't keep Sasha's value — no link")
            filled.append({"name": v["export"], "label": v["export"], "value": got})
        lap("fill")
        if school == "yale":                         # its 2nd page holds the tour times
            if not await page.press_continue():
                raise HO.Refused("unexpected_step", "Yale's form has no Continue where it should — no link")
            if not await page.tick_time(session.start):
                raise HO.Refused("not_all_prefilled", f"Yale's form didn't offer {session.start} after Continue — no link")
            filled.append({"name": "session", "label": "session", "value": f"{title} {session.start}"})
        seen = await page.read_slate()
        empty = [q["label"] or q["export"] for q in seen["qs"] if q["required"] and q["visible"] and not q["value"]
                 and (q["export"] or "") not in NOT_OURS]
        if empty:
            raise HO.Refused("not_all_prefilled", f"their form still needs: {', '.join(empty)} — no link")
        if seen["captcha"]:
            raise HO.Refused("captcha", "a CAPTCHA appeared while filling — no link")
        rec["filled"] = filled
        box = FAMILY_BOXES.get(school)
        rec["book_label"] = await (page.page.evaluate(HO._POINT_BOX_JS, [SUBMIT, box[0], box[1]]) if box
                                   else page.page.evaluate(HO._POINT_JS, SUBMIT))
        if not rec["book_label"]:
            raise HO.Refused("unexpected_step", f"{s['name']}'s Submit isn't where it should be — no link")
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
        log.warning("[campus-tour] %s failed: %s: %s", hid, type(e).__name__, e)
        raise HO.Refused("handover_failed", f"the cloud browser couldn't prepare {s['name']}'s form ({type(e).__name__}) — no link") from None
    rec["_page"] = page
    rec["_watch"] = asyncio.ensure_future(_watch(rec))
    HO.HANDOVERS[hid] = rec
    log.info("[campus-tour] %s ready in %sms: %s (read_only=%s)", hid, rec["ready_ms"], rec["venue"], read_only)
    return rec


FICTIONAL_FAMILY = {"parent_name": "Padre Ejemplo", "student_first": "Prueba", "student_last": "Sasha", "email": "prueba@example.com",
                    "parent_email": "padre@example.com", "mobile": "2025550123", "high_school": "Kanoe Test High School",
                    "grad_year": "2027", "major": "Engineering", "birthdate": "2009-03-14",
                    "address": "100 Example Street, Princeton, NJ 08540", "party": "3"}
