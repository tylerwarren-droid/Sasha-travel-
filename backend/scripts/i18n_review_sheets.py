"""CR 7 · generate the native-review sheet for each language's venue emails (docs/sasha/i18n/emails/{lang}-review.md).

    cd backend && python -m scripts.i18n_review_sheets          # writes all 12; tests fail if a sheet is out of date

A reviewer marks each line ✅ accept or ✏ fix (with the corrected text), signs at the bottom, and the language goes live
with ONE line in booking_signer/i18n/emails/__init__.py: REVIEWED["xx"] = ("Reviewer Name", "YYYY-MM-DD").
"""
from __future__ import annotations

import pathlib

from booking_signer.i18n import emails as I

OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "sasha" / "i18n" / "emails"
TITLES = {"request_table": "1. Table request", "request_generic": "2. Booking request (anything that isn't a table)",
          "cancel": "3. Cancellation", "confirm": "4. After a call: confirming in writing what they agreed",
          "ask": "5. After an unclear call: could you confirm in writing?"}
SAMPLE_COUNTS = (1, 2, 3, 5, 11, 12, 21, 22, 25)


def sheet(lang: str) -> str:
    m = I.mod(lang)
    lines = [f"# {m.NAME} ({lang}) — venue emails: native-review sheet", "",
             f"**Status: {m.STATUS}.** These texts were written by an AI and have NOT been checked by a native speaker. Until "
             "this sheet is signed, they are sent ONLY to Kanoe's own test addresses. Real venues get the English email, as "
             "today.", "",
             "**How to review:** read each line in the language. Tick ✅ if it is correct, natural and polite for a business writing to a "
             "restaurant or other venue. Otherwise mark ✏ and write the corrected text. Check above all that: (1) it says FIRST "
             "that Sasha is an AI; (2) the guest's name, date, time and party are clear; (3) it asks the venue to reply IN "
             "WRITING; (4) nothing promises a deposit, a fee or another time.", "",
             "Placeholders in {braces} are filled in automatically: {name}/{who}/{guest_short} the guest's name, {d} the "
             "date (YYYY-MM-DD), {t} the time (HH:MM), {n} the party, {what} what is booked, {core} the booking line below, {me} "
             "Sasha's address.", "",
             "## The AI disclosure (the same words are used on phone calls)", "",
             f"> {m.DISCLOSURE}", "", "- [ ] ✅ accept   - [ ] ✏ fix: ______", "",
             "## The booking line ({core})", "", f"> {m.CORE}", "", f"Back-translation: *{m.CORE_BACK}*", "",
             "- [ ] ✅ accept   - [ ] ✏ fix: ______", "",
             "## Counting people", "", "| n | text |", "|---|---|"]
    lines += [f"| {n} | {I.count(lang, n)} |" for n in SAMPLE_COUNTS]
    lines += ["", "- [ ] ✅ all correct   - [ ] ✏ fix: ______", ""]
    for kind in I.KINDS:
        subj, body = m.T[kind]
        bsubj, bbody = m.BACK[kind]
        lines += [f"## {TITLES[kind]}", "", "| # | Text | Back-translation (English) | ✅ / ✏ fix |", "|---|---|---|---|",
                  f"| S | {subj} | {bsubj} | |"]
        paras, bparas = body.split("\n\n"), bbody.split("\n\n")
        for i, p in enumerate(paras, 1):
            bp = bparas[i - 1] if i - 1 < len(bparas) else ""
            lines.append(f"| {i} | {p.replace(chr(10), '<br>')} | {bp.replace(chr(10), '<br>')} | |")
        lines.append("")
    lines += ["## Sign-off", "", "Reviewer (native speaker): ____________________   Date: ____________", "",
              "I confirm the texts above, with the fixes marked, are correct and appropriate for venues.", "",
              f"*Then, in `booking_signer/i18n/emails/__init__.py`: `REVIEWED[\"{lang}\"] = (\"Reviewer Name\", \"YYYY-MM-DD\")` "
              "— after the fixes are applied to the language file.*", ""]
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for lang in I.LANGS:
        (OUT / f"{lang}-review.md").write_text(sheet(lang), encoding="utf-8")
    print(f"wrote {len(I.LANGS)} review sheets to {OUT}")


if __name__ == "__main__":
    main()
