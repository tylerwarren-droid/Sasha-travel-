"""CR 65 · EU 212's 5-minute demo script, PLAYED IN A BROWSER (Playwright), beat by beat — the console, the customer's booking page,
the customer's phone, the test drawer playing the suppliers (sandbox.supplier_reply: no real phone), the proof panel, and the
failure beat. Used by the Docker build (tests/test_e2e.py, against fakes) and live:

    DIVE_CONSOLE_TOKEN=… python -m dive_service.e2e_demo --base https://agapi-dive-demo-production.up.railway.app --runs 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

from playwright.sync_api import expect, sync_playwright

T = 20_000   # ms: the console refreshes every 3 s


def _wd(w: int, after: int = 2) -> str:
    d = date.today() + timedelta(days=after)
    while d.weekday() != w:
        d += timedelta(days=1)
    return d.isoformat()


def _answer(page, supplier: str, button: str) -> None:
    """The drawer plays a supplier's answer; the step ends when that leg stops waiting (it leaves the drawer) — never a fixed pause."""
    card = page.locator(f"[data-testid=drawer-leg][data-supplier='{supplier}']")
    expect(card).to_have_count(1, timeout=T)
    card.locator("button", has_text=button).click()
    expect(card).to_have_count(0, timeout=T)


def run(base: str, token: str, log=print, headless: bool = True, slow_ms: int = 0) -> None:
    """On a failure, a screenshot of every open page goes to $DIVE_E2E_SHOTS (if set), so a live failure is seen, not guessed."""
    base = base.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context()
        if slow_ms:   # the build plays the network's delay on every console call, so a race shows up there, not live
            def _slow(route):
                time.sleep(slow_ms / 1000)
                route.continue_()
            ctx.route("**/console/api/**", _slow)
        page = ctx.new_page()
        try:
            _script(base, token, log, ctx, page)
        except Exception:
            shots = os.environ.get("DIVE_E2E_SHOTS")
            if shots:
                for i, pg in enumerate(ctx.pages):
                    pg.screenshot(path=os.path.join(shots, f"fail-{i}.png"), full_page=True)
            raise
        finally:
            browser.close()


def _script(base: str, token: str, log, ctx, page) -> None:
    if True:
        auth = {"Authorization": f"Bearer {token}", "content-type": "application/json"}

        def op(name, body=None):
            r = page.request.post(f"{base}/op/v1/{name}", headers=auth, data=json.dumps(body or {}))
            j = r.json()
            assert j["ok"], (name, j)
            return j["result"]

        def step(x):
            log(f"  ✓ {x}")

        op("operators.put", {"slug": "blue-kyma", "name": "Blue Kyma Diving (demo)", "timezone": "Europe/Athens", "languages": ["en", "el"],
                             "site_url": base + "/fake/blue-kyma"})
        # CR 66 · Tyler's door: the start page (behind the console token) → [Reset demo] → step 2's link, #find
        page.goto(f"{base}/start")
        page.fill("input[name=token]", token)
        page.click("text=Open the console")
        expect(page.locator("h1")).to_have_text("Run the DIVE demo")
        expect(page.locator("[data-testid=beat]")).to_have_count(10)
        page.click("[data-testid=reset]")
        expect(page.locator("[data-testid=reset-done]")).to_be_visible(timeout=T)
        expect(page.locator("[data-testid=state]")).to_contain_text("0 suppliers confirmed · 0 channels verified · package not published · 0 booking(s)")
        start = page
        with ctx.expect_page() as find_i:
            start.click("[data-testid=beat-2]")
        page = find_i.value
        expect(page.locator("h1")).to_contain_text("Blue Kyma Diving")
        expect(page.locator("[data-testid=find]")).to_be_focused(timeout=T)
        step("the start page: 10 steps, each one link; Reset demo → an empty console; step 2 opens the console at Find suppliers")
        # 0:30–1:15 · Find suppliers → 5 drafts → Confirm ×4 / Not ours → channels → verification → the boat's YES
        page.click("text=Find suppliers on my site")
        expect(page.get_by_text("Rival Boats", exact=True)).to_be_visible(timeout=T)
        expect(page.locator("text=instruction-like: ignored")).to_be_visible()
        for n in ("Aegean Boats", "Kyma Gear", "Taverna Agios", "Hotel Kyma View"):
            page.locator(".card", has_text=n).filter(has=page.locator("button", has_text="Confirm")).locator("button", has_text="Confirm").click()
            expect(page.locator(".card", has_text=n).locator("button", has_text="Confirm")).to_have_count(0, timeout=T)
        page.locator(".card", has_text="Rival Boats").locator("button", has_text="Not ours").click()
        expect(page.get_by_text("Rival Boats", exact=True)).to_have_count(0, timeout=T)
        step("Find suppliers: 5 drafts, each quoting its sentence; the injection flagged; 4 confirmed, Rival Boats: Not ours")
        for n, use in (("Aegean Boats", "Use whatsapp"), ("Kyma Gear", "Use email"), ("Taverna Agios", "Use web form"), ("Hotel Kyma View", "Use feed")):
            page.locator(".card", has_text=n).locator("button", has_text=use).click()
            expect(page.locator(".card", has_text=n).locator("button", has_text="Send verification")).to_have_count(1, timeout=T)
            page.locator(".card", has_text=n).locator("button", has_text="Send verification").click()
            expect(page.locator("[data-testid=msg]")).to_contain_text(n, timeout=T)       # its answer — never a fixed pause
        page.click("text=Test drawer")
        for n in ("Aegean Boats", "Kyma Gear"):
            card = page.locator(".card", has_text=f"{n} · verification sent")
            expect(card).to_have_count(1, timeout=T)
            card.locator("button", has_text="Supplier: YES").click()
            expect(card).to_have_count(0, timeout=T)                                       # verified: it leaves the drawer
        page.click("text=Suppliers")
        expect(page.locator("text=✓ verified")).to_have_count(4, timeout=T)
        step("verification: the boat and the gear shop replied YES (played in the drawer); the form dry-run and the feed search passed — 4 ✓ verified")
        # 1:15–1:45 · publish → the docs, under the operator's name
        page.click("text=Packages")
        page.click("text=Create “Discover Mykonos”")
        page.click("button:has-text('Publish')")
        expect(page.locator("text=Published").first).to_be_visible(timeout=T)
        page.click("text=API & keys")
        with ctx.expect_page() as docs_i:
            page.click("text=Open my docs")
        docs = docs_i.value
        expect(docs.locator("h1")).to_have_text("Blue Kyma Diving API")
        expect(docs.locator("footer")).to_contain_text("Blue Kyma API · powered by AgAPI")
        docs.close()
        step("published: the docs page is titled 'Blue Kyma Diving API', footer 'Blue Kyma API · powered by AgAPI'")
        # 1:45–2:30 · the customer: the booking page → the read-back → the tap on their phone
        cust = ctx.new_page()
        cust.goto(f"{base}/o/blue-kyma/book")
        cust.fill("input[name=date]", _wd(1))
        cust.select_option("select[name=party]", "4")
        cust.fill("input[name=name]", "Marta Ruiz")
        cust.fill("input[name=phone]", "+15005550101")
        cust.click("text=See the read-back")
        expect(cust.locator("text=We sent the link to your phone")).to_be_visible(timeout=T)
        for leg in ("Aegean Boats · confirmed by the boat", "Kyma Gear · confirmed by email", "Taverna Agios · booked on their form", "instant (feed)"):
            expect(cust.locator(".card", has_text=leg)).to_have_count(1)
        with ctx.expect_page() as phone_i:
            cust.click("text=open it as the customer's phone")
        phone = phone_i.value
        # CR 66 · the start page's phone link points at this same link (read, not opened: each opening issues a new one-time form code)
        loc = page.request.get(f"{base}/start/phone", max_redirects=0).headers.get("location", "")
        assert phone.url.endswith(loc) and "/o/blue-kyma/a/" in loc, "the start page's phone link isn't the newest link on the customer's phone"
        phone.click("text=Yes, book it")
        expect(phone.locator("#out")).to_contain_text("Waiting for", timeout=T)
        step("the customer saw every leg and how it's confirmed, and tapped Yes once on their phone")
        # 2:30–3:30 · the legs: the form confirms; the gear and the boat answer (played) → Confirmed
        page.click("text=Bookings")
        expect(page.locator("[data-testid=leg][data-supplier='Taverna Agios'][data-state=confirmed]")).to_have_count(1, timeout=T)
        page.click("text=Test drawer")
        _answer(page, "Kyma Gear", "Supplier: YES")
        _answer(page, "Aegean Boats", "ΝΑΙ")
        page.click("text=Bookings")
        expect(page.locator("[data-testid=booking][data-state=confirmed]")).to_have_count(1, timeout=T)
        expect(phone.locator("#out")).to_contain_text("All confirmed. Here's your plan.", timeout=T)
        step("the taverna confirmed on its form; Kyma Gear YES; Aegean Boats ΝΑΙ; the hotel booked → ✓ Confirmed (and on the customer's phone)")
        # 3:30–4:00 · proof
        page.locator("[data-testid=leg][data-supplier='Aegean Boats']").locator("button", has_text="Proof").click()
        expect(page.locator("[data-testid=proof-verdict]")).to_have_text("✓ The record matches.", timeout=T)
        expect(page.locator("[data-testid=proof-panel]")).to_contain_text("ΝΑΙ")
        page.click("[data-testid=proof-verify]")
        expect(page.locator("[data-testid=proof-verdict]")).not_to_have_text("Checking…", timeout=T)    # the fresh check's answer
        expect(page.locator("[data-testid=proof-verdict]")).to_have_text("✓ The record matches.")
        page.click("[data-testid=proof-close]")
        expect(page.locator("[data-testid=proof-panel]")).to_be_hidden()
        step("the boat's proof: what we sent, their ΝΑΙ, the hashes — Verify: ✓ The record matches.")
        page.goto(f"{base}/start/proof")                                                    # CR 66 · the start page's Proof link
        expect(page.locator("[data-testid=proof-panel]")).to_be_visible(timeout=T)
        expect(page.locator("[data-testid=proof-verdict]")).to_have_text("✓ The record matches.", timeout=T)
        expect(page.locator("[data-testid=proof-panel]")).to_contain_text("CONFIRMED")
        page.click("[data-testid=proof-close]")
        step("the start page's Proof link opens the whole booking's proof: ✓ The record matches.")
        # 4:00–4:40 · the failure beat: Thursday, the boat says NO — opened from the start page's step 9 (#drawer)
        start.reload()
        with ctx.expect_page() as drawer_i:
            start.click("[data-testid=beat-9]")
        page = drawer_i.value
        page.click("[data-testid=test-quote]")
        expect(page.locator("[data-testid=booking]")).to_have_count(2, timeout=T)          # it lands on Bookings with Thursday in it
        page.click("text=Test drawer")
        _answer(page, "Kyma Gear", "Supplier: YES")
        _answer(page, "Aegean Boats", "NO, full")
        page.click("text=Bookings")
        failed = page.locator("[data-testid=booking][data-state=failed]")
        expect(failed).to_have_count(1, timeout=T)
        expect(failed.locator("[data-testid=sentence]")).to_contain_text("Aegean Boats can't take your group on Thu")
        expect(failed.locator("[data-testid=sentence]")).to_contain_text("Nothing has been charged.")
        expect(failed.locator("[data-testid=leg][data-state=released]")).to_have_count(3)
        expect(failed.locator("text=Offer another time")).to_have_count(1)
        step("failure beat: 'Aegean Boats can't take your group on Thu … Nothing has been charged.' — 3 legs released; Offer another time")
        # nothing real went anywhere
        cap = page.request.post(f"{base}/console/api/captured.list", headers=auth, data="{}").json()["result"]["messages"]
        assert not [m for m in cap if m["real"]], "a REAL message went out"
        step("0 messages to a real number or inbox")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--gap", type=int, default=65)
    a = ap.parse_args()
    tok = os.environ.get("DIVE_CONSOLE_TOKEN", "")
    if not tok:
        print("set DIVE_CONSOLE_TOKEN (never printed)")
        return 2
    for n in range(1, a.runs + 1):
        if n > 1:
            time.sleep(a.gap)
        print(f"\n── Playwright run {n} · {a.base}")
        try:
            run(a.base, tok)
        except Exception as e:
            print(f"✕ run {n}: {type(e).__name__}: {str(e)[:600]}")
            return 1
    print(f"\nPLAYWRIGHT DEMO: {a.runs}/{a.runs} runs green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
