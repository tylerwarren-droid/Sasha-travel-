"""CR 1 · CampusMe's live proof — READ ONLY: the real reader against Yale's and Penn's own calendars, as a family's ask
would, then each school's registration form read and prepared for a FICTIONAL student. Nothing is submitted (the reader
has no submit). Every request is listed with its sha256 in docs/campusme/READS.md.

    cd backend && python -m scripts.campusme_live_read "Yale and Penn in November for my son"
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import datetime, timezone

from products.campus import handover as HV, request as RQ, schools as SC, slate as SL, turn as CT

FICTIONAL = {"first": "Sam", "last": "Ejemplo", "email": "sam.ejemplo@example.com", "birthdate": "2009-03-14",
             "high_school": "Example High School", "grad_year": "2028"}
OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "campusme" / "READS.md"


async def main(ask_text: str) -> None:
    now = datetime.now(timezone.utc)
    a = RQ.parse(ask_text, now.date())
    found = await CT.find(a, now.date())
    lines = [f"# CampusMe live reads — {now:%Y-%m-%d %H:%M} UTC", "",
             f"Ask: “{ask_text}” → schools {[s['name'] for s in a.schools]}, {a.when_words()}, {1 + a.guests} attendees.",
             "Read-only. Robots read first on each host; ≤ 1 request / 4 s per host; User-Agent `" + SL.UA + "`.", "",
             "## What a family would see", ""]
    n = 0
    for f in found:
        s = SC.SCHOOLS[f["school"]]
        lines.append(f"**{s['name']}** — published until {f['published_until']}" + (f" · {f['why']}" if f["why"] else ""))
        for x in f["sessions"]:
            n += 1
            lines.append("    " + CT.card_line(n, x).replace("\n", " · "))
        lines.append("")
    lines += ["## The hand-over, prepared for a fictional student (never submitted)", ""]
    for f in found:
        if not f["sessions"]:
            continue
        x = f["sessions"][0]
        s = SC.SCHOOLS[f["school"]]
        sess = SL.Session(**x)
        qs, challenge, receipt, pages = await SL.form(sess.form_url)
        rows = HV.plan(qs, FICTIONAL, sess, 1 + a.guests, "a fictional profile")
        c = HV.counts(rows)
        lines.append(f"**{s['name']}** — {sess.form_url} · {len(qs)} questions · {pages} page(s) · CAPTCHA marker: "
                     f"{'yes' if challenge else 'none in the served page'} · {c}")
        for r in rows:
            if r["action"] in ("fill", "choose", "you"):
                lines.append(f"    - [{r['action']}] {r['label'][:70]}" + (f" → {r['answer']}" if r["answer"] else "") +
                             (f" ({r['note']})" if r["note"] and r["action"] == "you" else ""))
        lines.append("")
    lines += ["## Every request (receipts)", "", "| # | url | HTTP | sha256 | at |", "|---|---|---|---|---|"]
    for i, r in enumerate(SL.READER.reads, 1):
        lines.append(f"| {i} | `{r['url']}` | {r['status']} | `{r['sha256'][:16]}…` | {r['at'][11:19]} |")
    posts = [r for r in SL.READER.reads if "cmd=counts" in r["url"]]
    lines += ["", f"POSTs: {len(posts)}, all Slate's own capacity read (`/register/form?cmd=counts`). No `cmd=submit` anywhere."]
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "Yale and Penn in November for my son"))
