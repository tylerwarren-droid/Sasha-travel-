"""CR 1 · the demo's controls: rehearse it end to end, and reset it in one command.

    railway run python -m scripts.cr1_demo rehearse [--n 1] [--account founder]   # default: the DEMO account; WhatsApp CAPTURED
    railway run python -m scripts.cr1_demo reset [campus|relocation|health|all] [--account founder|demo] [--vault]
    railway run python -m scripts.cr1_demo health
    railway run python -m scripts.cr1_demo showcase          # two PUBLIC example pages, fictional people, kept to 31 Dec
    railway run python -m scripts.cr1_demo officer           # CR 8 · the case officer's queue (made once; then its URL)

REHEARSE runs docs/products/CR-1-demo.md through the REAL code: the real WhatsApp turn (guest_whatsapp.turn and the
CR 1 hook), the real schools' calendars (read-only, paced), the real vault (KMS) and the real model (on the PUBLISHED
SPECIMEN passport, RvIG 2014, CC0), real Postgres (product_cases, trip_items) — as the DEMO account
(11111111-…). WhatsApp is the one thing faked: every message is CAPTURED, nothing reaches a phone, and the sandbox's
one-message-per-3.1-s pace is added to each beat's time so the timings are what the room will see. The transcript and
timings go to docs/products/rehearsals/.

RESET puts an account back to before the demo: its CampusMe and/or relocation cases (and the pages they back), the
campus visits CR 1 added to its bookings, and a product mode left open on its WhatsApp. --vault also revokes its saved
CampusMe student details (to show the five questions again). Nothing else of the account's is touched.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import List, Optional

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPECIMEN = ROOT / "docs" / "products" / "specimen" / "NL-passport-specimen-2014-RvIG-CC0.jpg"
OUT = ROOT / "docs" / "products" / "rehearsals"
DEMO = "11111111-1111-4111-8111-111111111111"
NUMBER = "+15555550142"          # a fictional number, linked in MEMORY only — never a real channel
SANDBOX_GAP = 3.1                # the sandbox sends one message every 3.1 s (guest_whatsapp.SEND_GAP)


def web() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/")


class Capture:
    """In place of guest_whatsapp.Sender: every message kept, none sent."""

    def __init__(self) -> None:
        self.sent: List[dict] = []
        self.asks: List[tuple] = []

    async def quick_reply(self, body, buttons):
        self.asks.append((body, buttons))
        return f"HX{len(self.asks)}"

    async def send(self, frm, to, *, body="", media=None, content_sid=None, variables=None):
        if content_sid:
            body, buttons = self.asks[int(content_sid[2:]) - 1]
            body = body + "\n[" + " · ".join(t for t, _ in buttons) + "]"
        self.sent.append({"body": body, "media": media})
        return "sent"


def _account(name: str) -> str:
    from booking_signer.identity import founder_account
    if name == "founder" and not os.getenv("FOUNDER_ACCOUNT_ID", "").strip():
        raise SystemExit("⛔ FOUNDER_ACCOUNT_ID isn't set on Railway: the founder's account isn't named. Use --account demo.")
    return DEMO if name == "demo" else founder_account()   # (since CR 3 they are the same account: 11111111-…)


async def _snapshot(account: str) -> dict:
    """What CR 1 rows the account has BEFORE a rehearsal — so the rehearsal removes only what IT made."""
    from booking_signer import routes as BR
    from booking_signer.vault import crypto as VC
    from products import itinerary as IT
    acct = uuid.UUID(account)

    async def q(c):
        cases = {r["id"] for r in await c.fetch("select id from product_cases where account_id = $1", acct)}
        visits = {str(r["id"]) for r in await c.fetch(
            "select ti.id from trip_items ti join trips t on t.id = ti.trip_id where t.owner_id = $1 "
            "and ti.type = 'experience' and ti.provider_name like '% campus visit — %'", acct)}
        clinic = {str(r["id"]) for r in await c.fetch(
            "select ti.id from trip_items ti join trips t on t.id = ti.trip_id where t.owner_id = $1 and ti.provider_name = $2",
            acct, "Kanoe Test Clinic")}
        clinic |= {str(r["id"]) for r in await c.fetch(   # CR 10 · the self-booked appointments the products add
            "select ti.id from trip_items ti join trips t on t.id = ti.trip_id where t.owner_id = $1 and ti.provider_name = any($2::text[])",
            acct, list(IT.OURS))}
        reads = {str(r["read_id"]) for r in await c.fetch(
            "select read_id from venue_reads where account_id = $1 and venue_name = 'Kanoe Test Clinic'", acct)}
        return cases, visits, clinic, reads
    cases, visits, clinic, reads = await BR.STORE._run(q)
    vault = {str(m["id"]) for m in await VC.STORE.list(account)}
    return {"cases": cases, "visits": visits, "vault": vault, "clinic": clinic, "reads": reads}


async def _clean_own(account: str, before: dict) -> dict:
    """Deletes ONLY the cases and campus visits this rehearsal created, and revokes ONLY the vault items it created
    (never a booking, a Google link or a vault item that was there before)."""
    from booking_signer import routes as BR
    from booking_signer.vault import crypto as VC
    from products import itinerary as IT
    from products.campus.turn import is_profile
    after = await _snapshot(account)
    new_cases, new_visits = after["cases"] - before["cases"], after["visits"] - before["visits"]
    new_clinic = [uuid.UUID(x) for x in after["clinic"] - before["clinic"]]
    new_reads = [uuid.UUID(x) for x in after["reads"] - before["reads"]]

    async def go(c):
        async with c.transaction():
            a = await c.execute("delete from product_cases where id = any($1::text[]) and coalesce(state->>'showcase','false') <> 'true'",
                                list(new_cases))
            b = await c.execute("delete from trip_items where id = any($1::uuid[]) and type = 'experience' "
                                "and provider_name like '% campus visit — %'", [uuid.UUID(x) for x in new_visits])
            # CR 4 · the test clinic's call: its rows go, so a rehearsal never counts against the real daily call cap
            await c.execute("delete from booking_attempts where trip_item_id = any($1::uuid[])", new_clinic)
            calls = await c.execute("delete from booking_calls where trip_item_id = any($1::uuid[])", new_clinic)
            d = await c.execute("delete from trip_items where id = any($1::uuid[]) and provider_name = any($2::text[])", new_clinic,
                                ["Kanoe Test Clinic", *IT.OURS])
            await c.execute("delete from venue_reads where read_id = any($1::uuid[]) and venue_name = 'Kanoe Test Clinic'", new_reads)
            return int(a.split()[-1]), int(b.split()[-1]) + int(d.split()[-1]), int(calls.split()[-1])
    n_cases, n_visits, n_calls = await BR.STORE._run(go)
    n_vault = 0
    now = datetime.now(timezone.utc)
    for m in await VC.STORE.list(account):
        if str(m["id"]) not in before["vault"] and is_profile(m):
            if await VC.STORE.revoke(account, m["id"], now):
                await VC.STORE.event(account, m["id"], "revoked", {"by": "cr1_demo rehearse — its own item"}, now)
                n_vault += 1
    return {"cases": n_cases, "bookings (campus visits, the clinic, CR 10 appointments)": n_visits, "call rows": n_calls,
            "vault items it created": n_vault}


async def _setup(account: str):
    from booking_signer import guest_whatsapp as GW, routes as BR
    from products import store as ST
    from products.campus import slate as SL
    from products.relocation import docread as DR
    kind = await ST.choose(BR.STORE)
    if kind != "postgres":
        raise SystemExit(f"⛔ product_cases isn't reachable ({kind}) — run this with `railway run`")
    GW.STORE, GW.SENDER = GW.MemoryGuestStore(), Capture()
    SL.READER = SL.Reader()                       # cold, as Railway's process is on the day: no cached reads
    small = tempfile.mktemp(suffix=".jpg")
    subprocess.run(["sips", "-Z", "1800", str(SPECIMEN), "--out", small], check=True, capture_output=True)

    async def specimen(url):                      # the "photo the person sent" is the published specimen
        return open(small, "rb").read(), "image/jpeg"
    DR.FETCH = specimen
    # CR 4 · the private-clinic call goes through Sasha's REAL call routes — with only Bland faked, in this process:
    # nothing is dialled, and Railway's own SASHA_CALLS_ENABLED (0) is untouched
    from booking_signer import call_routes as CR, calls as CL
    os.environ["SASHA_CALLS_ENABLED"] = "1"
    os.environ["SASHA_TEST_CALL_NUMBER"] = "+34600000000"     # a fictional number: the fake Bland never dials anything
    real_http = CR.HTTP

    class _R:
        def __init__(self, status, body):
            self.status_code, self._b = status, body

        def json(self):
            return self._b

    async def fake_bland(method, url, **kw):
        if url == CL.BLAND_CALLS_URL:
            return _R(200, {"status": "success", "call_id": f"rehearsal-{uuid.uuid4().hex[:12]}"})
        return await real_http(method, url, **kw)
    CR.HTTP = fake_bland
    GW._spawn = lambda coro: coro.close()                       # no call watcher: there is no call to watch
    key = GW.wa_key(NUMBER)
    now = datetime.now(timezone.utc)
    await GW.STORE.link({"account_id": account, "wa_id_sha256": key, "number_e164": NUMBER, "linked_at": now, "consent_at": now,
                         "consent_wording_version": "v3", "consent_text_sha256": GW.consent("v3")["sha256"]})
    return GW, key


async def _live_one(account: str, text: str) -> list:
    """CR 15 · ONE real WhatsApp message to the account's own linked number, through the same deliver() every turn uses —
    so the 24-hour window and STOP still decide (sandbox: no templates)."""
    from booking_signer import guest_whatsapp as GW, routes as BR
    store = GW.PostgresGuestStore(BR.STORE)
    ch = await store.channel_of_account(account)
    if not ch:
        return ["not sent: this account has no linked WhatsApp"]
    st = await store.get_state(ch["wa_id_sha256"])
    captured, GW.SENDER = GW.SENDER, GW.Sender()
    try:
        return await GW.deliver(ch, "+14155238886", GW.Out().text(text), st.get("last_inbound_at"))
    finally:
        GW.SENDER = captured


async def _say(GW, key, body="", payload="", media=False):
    ch = await GW.STORE.channel_for(key)
    p = {"From": f"whatsapp:{NUMBER}", "To": "whatsapp:+14155238886", "Body": body, "ButtonPayload": payload}
    if media:
        p.update(NumMedia="1", MediaUrl0="https://api.twilio.com/specimen", MediaContentType0="image/jpeg")
    before = len(GW.SENDER.sent)
    t = time.monotonic()
    await GW.turn(ch, "+14155238886", p)
    took = time.monotonic() - t
    new = GW.SENDER.sent[before:]
    return took, new


def _button(GW, i: int) -> str:
    return GW.SENDER.asks[-1][1][i][1]


def _page(path: str) -> tuple:
    t = time.monotonic()
    try:
        with urllib.request.urlopen(f"{web()}{path}", timeout=60) as r:
            body = r.read()
            return time.monotonic() - t, r.status, body
    except Exception as e:
        return time.monotonic() - t, getattr(e, "code", 0), b""


async def rehearse(n: int, account_name: str = "demo", only: Optional[str] = None) -> pathlib.Path:
    account = _account(account_name)
    GW, key = await _setup(account)
    before = await _snapshot(account)
    from booking_signer.vault import crypto as VC
    from products.campus.turn import is_profile
    has_vault = any(is_profile(r) for r in await VC.STORE.list(account))
    rows, t0 = [], time.monotonic()

    async def beat(label, body="", payload="", media=False, expect=None):
        took, new = await _say(GW, key, body, payload, media)
        said = "\n".join(m["body"] + (f"  📎 {m['media']}" if m["media"] else "") for m in new)
        ok = (expect is None) or (expect in said)
        rows.append({"beat": label, "sent": body or payload or ("📷 specimen photo" if media else ""), "compute_s": round(took, 1),
                     "msgs": len(new), "room_s": round(took + SANDBOX_GAP * len(new), 1), "ok": ok, "said": said,
                     "expect": expect})
        print(f"{'✓' if ok else '✗'} {label:<34} {took:5.1f}s + {len(new)} msg → {rows[-1]['room_s']:5.1f}s", flush=True)
        if not ok:
            print("    said: " + said.replace("\n", " | ")[:400], flush=True)
        return said

    def page(label, path, expect):
        took, status, body = _page(path)
        ok = status == 200 and expect.encode() in body
        rows.append({"beat": label, "sent": f"GET {path}", "compute_s": round(took, 1), "msgs": 0, "room_s": round(took, 1),
                     "ok": ok, "said": f"HTTP {status}, {len(body)} bytes", "expect": expect})
        print(f"{'✓' if ok else '✗'} {label:<34} {took:5.1f}s (HTTP {status})", flush=True)

    try:   # a crash still cleans up what this rehearsal made, and says where it stopped
        if only == "us":   # CR 12 · one US consulate, end to end: New Jersey → New York's own page, its email, the pack
            await beat("U1 relocation", "relocation", expect="I never file anything")
            await beat("U2 first", "first", expect="economic resources")
            await beat("U3 me", "me", expect="present the application")
            await beat("U4 myself", "myself", expect="Your passport number?")
            said = await beat("U5 DEMO → prepared", "DEMO", expect="Your EX-01 is prepared")
            rid = said.split("/relocation-file/")[1][:22] if "/relocation-file/" in said else ""
            await beat("U6 SIGNED", "SIGNED", expect="Which country do you live in now?")
            await beat("U7 USA → which state", "USA", expect="Which US state")
            await beat("U8 New Jersey → New York's own page", "New Jersey", expect="Consulado General de España en Nueva York")
            await beat("U9 pack 1 3 4 6-8", "1 3 4 6-8", expect="Your document pack, in Consulado General de España en Nueva York")
            page("U10 file page: email + pack", f"/relocation-file/{rid}", "The appointment email")
            page("U11 file page: the pack", f"/relocation-file/{rid}", "05_Proof-of-economic-means")
            await beat("U12 entry date → the TIE, from its page", "1 March 2027", expect="I'll remind you here")
            await beat("U13 consulate booked → itinerary", "consulate booked 12 November 10:00", expect="booked by you")
        elif only == "modes":   # CR 15 · the mode words exactly as the founder types them; then ONE live message
            for label, msg, expect in (
                    ("M1 relocate", "relocate", "I never file anything"),
                    ("M2 sasha → back", "sasha", "Back to Sasha"),
                    ("M3 campus", "campus", "CampusMe here"),
                    ("M4 sasha → back", "sasha", "Back to Sasha"),
                    ("M5 españa → the menu", "españa", "EspañaMe"),
                    ("M6 2 → padrón (CONCEPT)", "2", "*What you need* (from the official page)"),
                    ("M7 5 → DGT (CONCEPT)", "5", "DGT — exchanging a foreign driving licence"),
                    ("M7b 3 → identity and access (CONCEPT)", "3", "Cl@ve"),
                    ("M7c 4 → social security and tax (CONCEPT)", "4", "Modelo 030"),
                    ("M7d 6 → education (CONCEPT)", "6", "Secretaría Virtual"),
                    ("M8 1 → Salud (LIVE) → consent", "1", "never why you need a doctor"),
                    ("M9 sasha → back", "sasha", "Back to Sasha"),
                    ("M10 espana (no ñ)", "espana", "EspañaMe"),
                    ("M11 sasha → back", "sasha", "Back to Sasha"),
                    ("M12 diligence", "diligence", "Applied Diligence — PREVIEW"),
                    ("M13 check TotalEnergies in France", "check TotalEnergies in France", "Applied Diligence"),
                    ("M14 the Netherlands → refused", "check Shell in the Netherlands", "terms don't allow passing on its records"),
                    ("M15 ad + a person → refused", "ad check Mr Patrick Pouyanné in France", "companies only"),
                    ("M16 sasha → back", "sasha", "Back to Sasha")):
                await beat(label, msg, expect=expect)
            if os.getenv("KANOE_LIVE_ONE", "1") == "0":   # a re-run: the one live message was already sent
                res = ["skipped: KANOE_LIVE_ONE=0 (already sent once)"]
            else:
                res = await _live_one(account, "🧪 Kanoe — one live check from today's rehearsal. The mode words for Wednesday: "
                                               "relocate · campus · españa · diligence · sasha (back to Sasha).")
            rows.append({"beat": "LIVE one real message to the account's own WhatsApp", "sent": "(live)", "compute_s": 0,
                         "msgs": 1, "room_s": 0, "ok": res == ["sent"] or all(str(x).startswith("SM") or x == "sent" for x in res),
                         "said": "; ".join(map(str, res)), "expect": "sent"})
            print(f"{'✓' if rows[-1]['ok'] else '✗'} LIVE message → {rows[-1]['said']}", flush=True)
        elif only == "trip":   # CR 13 · the products and Sasha's travel together — relocation, then campus
            for i, t in enumerate(("relocation", "first", "me", "myself", "DEMO", "SIGNED", "UK", "SKIP", "1 March 2027"), 1):
                await beat(f"T{i} {t}", t)
            await beat("TR1 book my flights → origin, once", "book my flights", expect="Which city will you fly from?")
            await beat("TR2 London → plan + Sasha's TEST flights", "London", expect="from Duffel in TEST mode")
            await beat("TR3 pick 1 → her read-back", payload=_button(GW, 0), expect="TEST")
            await beat("TR4 her one yes → TEST checkout", payload=_button(GW, 0), expect="checkout.stripe.com")
            await beat("TR5 NEXT → the hotel near the new address", "NEXT", expect="Hotels for 3 nights")
            await beat("TR6 NEXT → one itinerary", "NEXT", expect="You can apply for your visa")

            async def visit(words, tag):
                said = await beat(f"{tag} cards", f"campus {words} in November for my son", expect="Read just now from")
                said = await beat(f"{tag} pick 1", "1")
                if "full name" in said:
                    for a in ("Sam Ejemplo", "sam.ejemplo@example.com", "14 March 2009", "Example High School"):
                        await beat(f"{tag} · {a}", a)
                    await beat(f"{tag} · 2028", "2028", expect="Keep Sam's details in your vault")
                    await beat(f"{tag} keep → read-back", payload="cm:save:yes", expect="Exactly what I'll do")
                await beat(f"{tag} yes → prepared", payload=_button(GW, 0), expect="✅ Prepared.")
                await beat(f"{tag} REGISTERED", "REGISTERED", expect="registered on your word")
            await visit("Yale", "TC-Yale")
            await visit("Penn", "TC-Penn")
            await beat("TC1 plan the trip around the visits", "plan the trip around the visits", expect="Which city will you fly from?")
            await beat("TC2 Chicago → plan, drive check, TEST flights", "Chicago", expect="by car")
            await beat("TC3 NEXT → hotel near the first campus", "NEXT", expect="Hotels for 1 night")
            await beat("TC4 NEXT → hotel near the second campus", "NEXT", expect="Hotels for 1 night")
            await beat("TC5 NEXT → one itinerary", "NEXT", expect="Your itinerary")
            # ── the same journeys on the WEB chat: Sasha's own conduct(), as this account (the Sasha tab wired web_turn, 7b3c1ed) ──
            from app.services.conductor import conduct
            hist, sid = [], f"rehearsal-{uuid.uuid4().hex[:8]}"

            async def wbeat(label, msg, expect):
                t = time.monotonic()
                try:
                    r = await conduct(msg, list(hist), user_id=account, session_id=sid)
                    said = (r.get("response") or "") + "".join(
                        f"\n[card: {(b.get('title') or b.get('type') or '')} · {len(b.get('options') or [])} options]" for b in (r.get("bookings") or [])
                        if isinstance(b, dict))
                    hist[:] = r.get("conversation_history") or hist + [{"role": "user", "content": msg}, {"role": "assistant", "content": said}]
                except Exception as e:
                    said = f"{type(e).__name__}: {e}"
                took = time.monotonic() - t
                ok = expect in said
                rows.append({"beat": label, "sent": f"web: {msg}", "compute_s": round(took, 1), "msgs": 1, "room_s": round(took, 1),
                             "ok": ok, "said": said, "expect": expect})
                print(f"{'✓' if ok else '✗'} {label:<34} {took:5.1f}s (web)", flush=True)
                if not ok:
                    print("    said: " + said.replace("\n", " | ")[:400], flush=True)
            await wbeat("W1 web: book my flights", "book my flights", "Which city will you fly from?")
            await wbeat("W2 web: London → plan + flights", "London", "Flights London")
            await wbeat("W3 web: next → hotel", "next", "A hotel near your new address")
            await wbeat("W4 web: next → one itinerary", "next", "Your itinerary")
            await wbeat("W5 web: plan the trip around the visits", "plan the trip around the visits", "Which city will you fly from?")
            await wbeat("W6 web: Chicago → plan + drive check", "Chicago", "by car")
            await wbeat("W7 web: what do I need to do this week?", "what do I need to do this week?", "")
        else:
            # ── Part 1 · CampusMe ──
            await beat("C1 April (not published)", "campus visits at Yale and Penn in April for my son", expect="hasn't published April 2027 yet")
            await beat("C2 November cards", "campus Yale and Penn in November for my son", expect="Read just now from")
            if has_vault:
                await beat("C3 pick 1 → vault read-back", "1", expect="CampusMe student details (Sam) from your vault")
            else:
                await beat("C3 pick 1 → five questions", "1", expect="full name")
                for a in ("Sam Ejemplo", "sam.ejemplo@example.com", "14 March 2009", "Example High School"):
                    await beat(f"C3 · {a}", a)
                await beat("C3 · 2028 → keep in vault?", "2028", expect="Keep Sam's details in your vault")
                await beat("C4 keep → read-back", payload="cm:save:yes", expect="Exactly what I'll do")
            said = await beat("C5 yes → prepared", payload=_button(GW, 0), expect="✅ Prepared.")
            cid = said.split("/campus-handover/")[1][:22] if "/campus-handover/" in said else ""
            page("C6 hand-over page", f"/campus-handover/{cid}", "prepared, not sent")
            await beat("C7 REGISTERED", "REGISTERED", expect="registered on your word")
            await beat("C8 vague confirmation stays", "Thank you for registering for a campus visit. We look forward to seeing you soon!",
                       expect="doesn't name")
            # ── Part 2 · relocation ──
            await beat("R1 relocation", "relocation", expect="I never file anything")
            await beat("R2 first", "first", expect="economic resources")
            await beat("R3 me", "me", expect="present the application")
            await beat("R4 myself", "myself", expect="Your passport number?")
            # CR 10 · one Sasha: a flight request mid-relocation goes to her own flow, in the same chat; then back where we were
            await beat("RF1 flights → Sasha's own answer", "book me flights to Madrid on 1 March", expect=GW.ASK_ONE[:30])
            await beat("RF2 relocation → where we were", "relocation", expect="Back to your EX-01. Your passport number?")
            await beat("R5 specimen photo → read", media=True, expect="check digit agrees")
            await beat("R6 yes, all right", payload="rx:doc:yes", expect="Kept")
            await beat("R7 surname", "De Bruijn")
            said = await beat("R8 DEMO → prepared", "DEMO", expect="Your EX-01 is prepared")
            rid = said.split("/relocation-file/")[1][:22] if "/relocation-file/" in said else ""
            page("R9 reviewer page", f"/relocation-file/{rid}", "LEFT FOR THE APPLICANT")
            page("R10 the PDF", f"/api/products/relocation/{rid}/EX-01-prepared.pdf", "%PDF")
            await beat("R11 SIGNED", "SIGNED", expect="Which country do you live in now?")
            await beat("R12 UK → consulate + checklist", "UK", expect="Consulado General de España en Londres")
            await beat("R13a pack 1 2 3 → in the sheet's order", "1 2 3", expect="Your document pack")   # CR 12
            await beat("R13 entry date → reminders", "1 March 2027", expect="I'll remind you here")
            await beat("R14 consulate booked → itinerary", "consulate booked 12 November 10:00", expect="booked by you")   # CR 10
            # ── Part 3 · health (CR 4) ──
            await beat("H1 health → consent", "health I need a doctor this week", expect="never why you need a doctor")
            await beat("H2 consent yes → choose", payload="hx:consent:yes", expect="A private clinic")
            await beat("H3 private", payload="hx:priv", expect="Which day and time")
            await beat("H4 Tuesday 10:00 → read-back", "Tuesday 10:00", expect="una cita con el médico general")
            await beat("H5 yes → the call", payload=_button(GW, 0), expect="📞")
            await beat("H7 health again → consent", "salud", expect="never why you need a doctor")
            await beat("H8 consent → choose", payload="hx:consent:yes", expect="A private clinic")
            said = await beat("H9 public (SERMAS) → hand-over", payload="hx:pub", expect="health-handover/")
            await beat("H10 DEMO → fictional patient", "DEMO", expect="health-handover/")
            hid = said.split("/health-handover/")[1][:22] if "/health-handover/" in said else ""
            page("H11 SERMAS hand-over page", f"/health-handover/{hid}", "Open SERMAS")
            await beat("H12 booked it → add?", "I booked it for 13 October at 10:00", expect="kept with your bookings")   # CR 10
            await beat("H12b yes → itinerary", payload="hx:sermas:yes", expect="Added to your itinerary")
            await beat("H13 health → consent", "health", expect="never why you need a doctor")
            await beat("H14 consent → choose", payload="hx:consent:yes", expect="A private clinic")
            said = await beat("H15 new in Madrid → checklist", payload="hx:new", expect="Padrón (town hall)")
            nid = said.split("/health-handover/")[1][:22] if "/health-handover/" in said else ""
            page("H16 checklist page", f"/health-handover/{nid}", "Your health card and your family doctor")
            await beat("H17 padrón date → reminders", "20 October 2026", expect="I'll remind you here")

            # ── Part 4 · the case officer (CR 8): the page, one return, the mark — then the queue put back as it was ──
            ocid = await _officer_id(create=True)
            kept = await _officer_returned(ocid)
            page("O1 officer queue", f"/officer/{ocid}", "need attention before they")
            t = time.monotonic()
            req = urllib.request.Request(f"{web()}/api/products/relocation/officer/{ocid}/return/A-1042", method="POST")
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    ok, said = r.status == 200 and b'"sent":false' in r.read().replace(b" ", b""), f"HTTP {r.status}"
            except Exception as e:
                ok, said = False, f"{type(e).__name__}: {e}"
            rows.append({"beat": "O2 return A-1042", "sent": "POST return/A-1042", "compute_s": round(time.monotonic() - t, 1), "msgs": 0,
                         "room_s": round(time.monotonic() - t, 1), "ok": ok, "said": said, "expect": "recorded, sent:false"})
            print(f"{'✓' if ok else '✗'} {'O2 return A-1042':<34} {rows[-1]['room_s']:5.1f}s ({said})", flush=True)
            page("O3 the mark on the page", f"/officer/{ocid}", "Returned to the applicant")
            await _officer_returned(ocid, kept)          # the queue as it was before the rehearsal
    except Exception as e:
        rows.append({"beat": "⛔ stopped", "sent": "", "compute_s": 0, "msgs": 0, "room_s": 0, "ok": False,
                     "said": f"{type(e).__name__}: {e}", "expect": "no crash"})
        print(f"⛔ stopped: {type(e).__name__}: {e}", flush=True)
    total = time.monotonic() - t0
    cleaned = await _clean_own(account, before)
    print("cleaned up its own rows: " + ", ".join(f"{k} {v}" for k, v in cleaned.items()), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    f = OUT / f"rehearsal-{n}{'-' + only if only else ''}-{stamp}.md"
    room = sum(r["room_s"] for r in rows)
    lines = [f"# CR 1 rehearsal {n} — {stamp} UTC", "",
             f"Real code, real schools, real vault, real model (published specimen), real Postgres, as the {account_name.upper()} "
             f"account ({account[:8]}…). "
             f"WhatsApp captured on a fictional number (nothing sent). Vault item present at start: {has_vault}. "
             f"Afterwards it removed only what it created: " + ", ".join(f"{k} {v}" for k, v in cleaned.items()) + ".", "",
             f"**Beats: {sum(r['ok'] for r in rows)}/{len(rows)} as expected · the room waits {room:.0f} s in all "
             f"(compute + {SANDBOX_GAP} s per sandbox message) · script wall time {total:.0f} s.**", "",
             "| beat | sent | compute s | msgs | the room waits s | ok |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['beat']} | {r['sent'][:60]} | {r['compute_s']} | {r['msgs']} | {r['room_s']} | {'✓' if r['ok'] else '✗ expected: ' + str(r['expect'])} |"
              for r in rows]
    lines += ["", "## What WhatsApp would have shown", ""]
    for r in rows:
        lines += [f"### {r['beat']}", f"> {r['sent']}", "", "```", r["said"], "```", ""]
    # the account's own mobile (Sasha's read-back names it: "If they ask for a contact number, I'll give yours") never
    # lands in a transcript that goes into the repo
    st, cj = await GW.api(account, "GET", "/api/booking/contact")
    mobile = ((cj or {}).get("contact") or {}).get("mobile_e164")
    text = "\n".join(lines)
    if mobile:
        text = text.replace(mobile, "[the account's mobile]")
    f.write_text(text)
    print(f"\n{sum(r['ok'] for r in rows)}/{len(rows)} beats ok · room {room:.0f}s · transcript {f.relative_to(ROOT)}")
    return f


async def reset(what: str, account_name: str, vault: bool) -> None:
    if what == "officer":                       # CR 8 · the queue stays (the site links it); its "returned" marks go
        cid = await _officer_id(create=False)
        if not cid:
            print("no officer queue yet — run: cr1_demo.sh officer")
            return
        n = len(await _officer_returned(cid, {}))
        print(f"reset officer: {n} 'returned' mark(s) cleared; the queue is at {web()}/officer/{cid}")
        return
    from booking_signer import routes as BR
    from booking_signer.identity import founder_account
    account = DEMO if account_name == "demo" else founder_account()   # reset may run on the fallback: it says so
    acct = uuid.UUID(account)
    products = ["campus", "relocation", "health"] if what == "all" else [what]

    async def go(conn):
        out = {}
        async with conn.transaction():
            out["product_cases"] = int((await conn.execute(
                "delete from product_cases where account_id = $1 and product = any($2::text[]) "
                "and coalesce(state->>'showcase', 'false') <> 'true'", acct, products)).split()[-1])   # the site's examples stay
            if "campus" in products:
                out["campus visits in bookings"] = int((await conn.execute(
                    "delete from trip_items where id in (select ti.id from trip_items ti join trips t on t.id = ti.trip_id "
                    "where t.owner_id = $1 and ti.type = 'experience' and ti.provider_name like '% campus visit — %')", acct)).split()[-1])
            if "health" in products:
                # the stand-in clinic's bookings and call rows (a live demo call leaves them); never any other booking
                ids = [r["id"] for r in await conn.fetch(
                    "select ti.id from trip_items ti join trips t on t.id = ti.trip_id where t.owner_id = $1 "
                    "and ti.provider_name = 'Kanoe Test Clinic'", acct)]
                await conn.execute("delete from booking_attempts where trip_item_id = any($1::uuid[])", ids)
                await conn.execute("delete from booking_calls where trip_item_id = any($1::uuid[])", ids)
                out["test-clinic bookings"] = int((await conn.execute(
                    "delete from trip_items where id = any($1::uuid[])", ids)).split()[-1])
                await conn.execute("delete from venue_reads where account_id = $1 and venue_name = 'Kanoe Test Clinic'", acct)
            from products import itinerary as IT   # CR 10 · consulate/TIE (relocation), SERMAS (health): by their own names only
            ours = ([IT.CONSULATE, IT.TIE] if "relocation" in products else []) + ([IT.SERMAS] if "health" in products else [])
            if ours:
                out["self-booked appointments in bookings"] = int((await conn.execute(
                    "delete from trip_items where id in (select ti.id from trip_items ti join trips t on t.id = ti.trip_id "
                    "where t.owner_id = $1 and ti.provider_name = any($2::text[]))", acct, ours)).split()[-1])
            out["open product mode on WhatsApp"] = int((await conn.execute(
                "update guest_wa_state set pending = null where pending->>'kind' = 'product' and pending->>'product' = any($2::text[]) "
                "and wa_id_sha256 in (select wa_id_sha256 from guest_channels where account_id = $1)", acct, products)).split()[-1])
        return out
    got = await BR.STORE._run(go)
    if vault and "campus" in products:
        from booking_signer.vault import crypto as VC
        from products.campus.turn import is_profile
        n = 0
        for m in await VC.STORE.list(account):
            if is_profile(m):
                if await VC.STORE.revoke(account, m["id"], datetime.now(timezone.utc)):
                    await VC.STORE.event(account, m["id"], "revoked", {"by": "cr1_demo reset"}, datetime.now(timezone.utc))
                    n += 1
        got["CampusMe vault items revoked"] = n
    linked = await BR.STORE._run(lambda c: c.fetchval(
        "select count(*) from guest_channels where account_id = $1 and channel = 'whatsapp'", acct))
    note = (" — FOUNDER_ACCOUNT_ID isn't set: the founder falls back to the demo account" if account_name == "founder"
            and not os.getenv("FOUNDER_ACCOUNT_ID", "").strip() else "")
    print(f"reset {what} for the {account_name} account ({account[:8]}…, {linked} WhatsApp linked{note}): "
          + ", ".join(f"{k} {v}" for k, v in got.items()))


SHOWCASE_UNTIL = "2026-12-31"
STUDENT = {"first": "Sam", "last": "Ejemplo", "email": "sam.ejemplo@example.com", "birthdate": "2009-03-14",
           "high_school": "Example High School", "grad_year": "2028"}


async def showcase() -> None:
    """Two PUBLIC example pages for the site (the Sasha tab links them): built by the real code — a live read of Yale's
    calendar and form, the real EX-01 fill and checker — for FICTIONAL people, marked fictional on the page. They belong
    to the demo account, carry state.showcase = true (reset never deletes them) and expire on SHOWCASE_UNTIL.
    Re-running makes new ids; the old ones stay until they expire."""
    from booking_signer import routes as BR
    from products import store as ST
    from products.campus import handover as HV, request as RQ, schools as SC, turn as CT
    from products.relocation import after as AF, checker as CK, ex01 as E, facts as F, turn as RT
    await ST.choose(BR.STORE)
    now = datetime.now(timezone.utc)
    a = RQ.parse("Yale in November for my son", now.date())
    f = (await CT.find(a, now.date()))[0]
    if not f["sessions"]:
        raise SystemExit(f"⛔ no open Yale session read: {f['why']}")
    from products.campus.slate import Session, form
    sess = Session(**f["sessions"][0])
    qs, challenge, receipt, pages = await form(sess.form_url)
    campus = {"school": "yale", "session": sess.as_dict(), "form_url": sess.form_url, "form_read": receipt, "form_pages": pages,
              "challenge_seen": challenge, "rows": HV.plan(qs, STUDENT, sess, 2, "a fictional student's details (illustration)"),
              "status": "handed_over", "fictional": True, "showcase": True}
    on = now.strftime("%-d %b %Y")
    facts = {"applicant": {k: F.fact(v, RT.FICTIONAL, on) for k, v in RT.DEMO.items()},
             "choices": {k: F.fact(v, RT.FICTIONAL, on) for k, v in
                         (("route", "initial"), ("resources", "self"), ("presenter", "self"), ("notices_to_own_address", "yes"))}}
    rows = CK.review(E.rows(facts, RT.applies(facts)), facts, now.date())
    E.fill(rows)
    reloc = {"facts": facts, "rows": rows, "counts": E.counts(rows), "checks": CK.summary(rows), "status": "prepared",
             "prepared_at": now.isoformat(), "route": "initial", "fictional": True, "showcase": True,
             "after": {"residence": "united kingdom", "consulate": AF.CONSULATES["united kingdom"],
                       "checklist": AF.checklist(facts, now.date(), "united kingdom"), "entry_date": "2027-03-01",
                       "reminders": AF.reminders("2027-03-01", now.date())}}
    ids = {}
    for product, state in (("campus", campus), ("relocation", reloc)):
        cid = ST.new_id()

        async def ins(conn, cid=cid, product=product, state=state):
            await conn.execute("insert into product_cases (id, product, account_id, wa_id_sha256, state, expires_at) "
                               "values ($1, $2, $3, 'showcase', $4::jsonb, $5::date)", cid, product, uuid.UUID(DEMO), state,
                               datetime.fromisoformat(SHOWCASE_UNTIL).date())
        await BR.STORE._run(ins)
        ids[product] = cid
    print(f"CampusMe:   {web()}/campus-handover/{ids['campus']}\nRelocation: {web()}/relocation-file/{ids['relocation']}\n"
          f"(fictional people, real forms; kept until {SHOWCASE_UNTIL}; reset never deletes them)")


async def _officer_id(create: bool) -> Optional[str]:
    """CR 8 · the ONE stable officer queue (the site links it): found, or made once. Showcase: never deleted by a reset."""
    from booking_signer import routes as BR
    from products import store as ST
    await ST.choose(BR.STORE)
    cid = await BR.STORE._run(lambda c: c.fetchval(
        "select id from product_cases where product = 'relocation' and state->>'kind' = 'officer_queue' "
        "and expires_at > now() order by created_at limit 1"))
    if cid or not create:
        return cid
    cid = ST.new_id()
    state = {"kind": "officer_queue", "showcase": True, "fictional": True, "returned": {}}

    async def ins(conn):
        await conn.execute("insert into product_cases (id, product, account_id, wa_id_sha256, state, expires_at) "
                           "values ($1, 'relocation', $2, 'showcase', $3::jsonb, $4::date)", cid, uuid.UUID(DEMO), state,
                           datetime.fromisoformat(SHOWCASE_UNTIL).date())
    await BR.STORE._run(ins)
    return cid


async def officer() -> None:
    cid = await _officer_id(create=True)
    print(f"Case officer queue (click-through, fictional): {web()}/officer/{cid}  (kept until {SHOWCASE_UNTIL}; reset officer "
          "clears the 'returned' marks, never the page)")


async def _officer_returned(cid: str, returned: Optional[dict] = None) -> dict:
    from booking_signer import routes as BR

    async def go(c):
        row = await c.fetchrow("select state from product_cases where id = $1", cid)
        st = row["state"] if isinstance(row["state"], dict) else json.loads(row["state"])
        before = dict(st.get("returned") or {})
        if returned is not None:
            st["returned"] = returned
            await c.execute("update product_cases set state = $2::jsonb, updated_at = now() where id = $1", cid, st)
        return before
    return await BR.STORE._run(go)


async def health() -> None:
    with urllib.request.urlopen(f"{web()}/api/products/health", timeout=30) as r:
        print(r.read().decode())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["rehearse", "reset", "health", "showcase", "officer"])
    ap.add_argument("what", nargs="?", default="all", choices=["all", "campus", "relocation", "health", "officer", "us", "trip", "modes"])
    ap.add_argument("--account", default="founder", choices=["founder", "demo"])
    ap.add_argument("--vault", action="store_true")
    ap.add_argument("--n", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "rehearse":
        asyncio.run(rehearse(a.n, a.account if "--account" in sys.argv else "demo", a.what if a.what in ("us", "trip", "modes") else None))
    elif a.cmd == "officer":
        asyncio.run(officer())
    elif a.cmd == "showcase":
        asyncio.run(showcase())
    elif a.cmd == "reset":
        asyncio.run(reset(a.what, a.account, a.vault))
    else:
        asyncio.run(health())


if __name__ == "__main__":
    main()
