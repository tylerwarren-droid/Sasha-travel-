"""CR 1 · the demo's controls: rehearse it end to end, and reset it in one command.

    railway run python -m scripts.cr1_demo rehearse [--n 1]   # both parts, as the DEMO account; WhatsApp CAPTURED
    railway run python -m scripts.cr1_demo reset [campus|relocation|all] [--account founder|demo] [--vault]
    railway run python -m scripts.cr1_demo health
    railway run python -m scripts.cr1_demo showcase          # two PUBLIC example pages, fictional people, kept to 31 Dec

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


async def _setup():
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
    key = GW.wa_key(NUMBER)
    now = datetime.now(timezone.utc)
    await GW.STORE.link({"account_id": DEMO, "wa_id_sha256": key, "number_e164": NUMBER, "linked_at": now, "consent_at": now,
                         "consent_wording_version": "v3", "consent_text_sha256": GW.consent("v3")["sha256"]})
    return GW, key


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


async def rehearse(n: int) -> pathlib.Path:
    GW, key = await _setup()
    from booking_signer.vault import crypto as VC
    from products.campus.turn import is_profile
    has_vault = any(is_profile(r) for r in await VC.STORE.list(DEMO))
    rows, t0 = [], time.monotonic()

    async def beat(label, body="", payload="", media=False, expect=None):
        took, new = await _say(GW, key, body, payload, media)
        said = "\n".join(m["body"] + (f"  📎 {m['media']}" if m["media"] else "") for m in new)
        ok = (expect is None) or (expect in said)
        rows.append({"beat": label, "sent": body or payload or ("📷 specimen photo" if media else ""), "compute_s": round(took, 1),
                     "msgs": len(new), "room_s": round(took + SANDBOX_GAP * len(new), 1), "ok": ok, "said": said,
                     "expect": expect})
        print(f"{'✓' if ok else '✗'} {label:<34} {took:5.1f}s + {len(new)} msg → {rows[-1]['room_s']:5.1f}s", flush=True)
        return said

    def page(label, path, expect):
        took, status, body = _page(path)
        ok = status == 200 and expect.encode() in body
        rows.append({"beat": label, "sent": f"GET {path}", "compute_s": round(took, 1), "msgs": 0, "room_s": round(took, 1),
                     "ok": ok, "said": f"HTTP {status}, {len(body)} bytes", "expect": expect})
        print(f"{'✓' if ok else '✗'} {label:<34} {took:5.1f}s (HTTP {status})", flush=True)

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
    await beat("C9 exit", "exit", expect="Back to Sasha")
    # ── Part 2 · relocation ──
    await beat("R1 relocation", "relocation", expect="I never file anything")
    await beat("R2 first", "first", expect="economic resources")
    await beat("R3 me", "me", expect="present the application")
    await beat("R4 myself", "myself", expect="Your passport number?")
    await beat("R5 specimen photo → read", media=True, expect="check digit agrees")
    await beat("R6 yes, all right", payload="rx:doc:yes", expect="Kept")
    await beat("R7 surname", "De Bruijn")
    said = await beat("R8 DEMO → prepared", "DEMO", expect="Your EX-01 is prepared")
    rid = said.split("/relocation-file/")[1][:22] if "/relocation-file/" in said else ""
    page("R9 reviewer page", f"/relocation-file/{rid}", "LEFT FOR THE APPLICANT")
    page("R10 the PDF", f"/api/products/relocation/{rid}/EX-01-prepared.pdf", "%PDF")
    await beat("R11 SIGNED", "SIGNED", expect="Which country do you live in now?")
    await beat("R12 UK → consulate + checklist", "UK", expect="Consulado General de España en Londres")
    await beat("R13 entry date → reminders", "1 March 2027", expect="I'll remind you here")
    await beat("R14 exit", "exit", expect="Back to Sasha")

    total = time.monotonic() - t0
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    f = OUT / f"rehearsal-{n}-{stamp}.md"
    room = sum(r["room_s"] for r in rows)
    lines = [f"# CR 1 rehearsal {n} — {stamp} UTC", "",
             f"Real code, real schools, real vault, real model (published specimen), real Postgres, as the DEMO account. "
             f"WhatsApp captured (nothing sent). Vault item present at start: {has_vault}.", "",
             f"**Beats: {sum(r['ok'] for r in rows)}/{len(rows)} as expected · the room waits {room:.0f} s in all "
             f"(compute + {SANDBOX_GAP} s per sandbox message) · script wall time {total:.0f} s.**", "",
             "| beat | sent | compute s | msgs | the room waits s | ok |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['beat']} | {r['sent'][:60]} | {r['compute_s']} | {r['msgs']} | {r['room_s']} | {'✓' if r['ok'] else '✗ expected: ' + str(r['expect'])} |"
              for r in rows]
    lines += ["", "## What WhatsApp would have shown", ""]
    for r in rows:
        lines += [f"### {r['beat']}", f"> {r['sent']}", "", "```", r["said"], "```", ""]
    f.write_text("\n".join(lines))
    print(f"\n{sum(r['ok'] for r in rows)}/{len(rows)} beats ok · room {room:.0f}s · transcript {f.relative_to(ROOT)}")
    return f


async def reset(what: str, account_name: str, vault: bool) -> None:
    from booking_signer import routes as BR
    from booking_signer.identity import founder_account
    account = DEMO if account_name == "demo" else founder_account()
    acct = uuid.UUID(account)
    products = ["campus", "relocation"] if what == "all" else [what]

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
    print(f"reset {what} for the {account_name} account: " + ", ".join(f"{k} {v}" for k, v in got.items()))


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


async def health() -> None:
    with urllib.request.urlopen(f"{web()}/api/products/health", timeout=30) as r:
        print(r.read().decode())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["rehearse", "reset", "health", "showcase"])
    ap.add_argument("what", nargs="?", default="all", choices=["all", "campus", "relocation"])
    ap.add_argument("--account", default="founder", choices=["founder", "demo"])
    ap.add_argument("--vault", action="store_true")
    ap.add_argument("--n", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "rehearse":
        asyncio.run(rehearse(a.n))
    elif a.cmd == "showcase":
        asyncio.run(showcase())
    elif a.cmd == "reset":
        asyncio.run(reset(a.what, a.account, a.vault))
    else:
        asyncio.run(health())


if __name__ == "__main__":
    main()
