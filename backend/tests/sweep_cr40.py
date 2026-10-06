"""CR 40 · RELIABILITY SWEEP — CampusMe, RelocateMe, EspañaMe: 15 natural phrasings each (vague, typos, Spanish/English, a change
of mind, "start over", switching between environments and back to "sasha"), through the WhatsApp turn with the captured sender,
on a GUEST account (the test harness's own; never the founder's). Each step is checked for: a reply at all (dead end), no error,
no model call, no identical reply twice running (a loop / a repeated question) — and the scenario's own expected answer.

    cd backend && python tests/sweep_cr40.py          # the table, per environment
    cd backend && python -m unittest tests.test_sweep_cr40
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from booking_signer import guest_whatsapp as GW  # noqa: E402
from tests import test_guest_whatsapp_s75 as TG  # noqa: E402

B = "__button__"   # ("__button__", payload) presses the last question's button whose id starts with payload


def P(prefix: str) -> Tuple[str, str]:
    return (B, prefix)


# (name, steps, expected-in-the-last-reply (any of), forbidden-anywhere)
CAMPUS = [
    ("bare keyword", ["campus"], ["CampusMe here"], []),
    ("all in one", ["campus visits at Yale on October 14 for my son"], ["Wed 14 Oct"], []),
    ("step by step", ["campus", "yale", "in october", "the 14th"], ["Wed 14 Oct"], []),
    ("lower case, no date words", ["campus", "yale october 14"], ["Wed 14 Oct"], []),
    ("Spanish", ["campus", "visitas a Yale el 14 de octubre para mi hijo"], ["Wed 14 Oct", "Yale"], []),
    ("a question mid-flow", ["campus", "what can you do?"], ["I read each university's own visit calendar"], []),
    ("change of mind", ["campus", "yale october 14", "actually penn on october 14"], ["Penn"], []),
    ("start over → yes", ["campus", "yale", "start over", P("so:yes:")], ["CampusMe here"], []),
    ("start over → no", ["campus", "yale", "start over", P("so:no:")], ["Back to your campus visits"], []),
    ("switch and back", ["campus", "yale", "relocation", "campus"], ["Back to your campus visits"], []),
    ("back to sasha", ["campus", "sasha"], ["Back to Sasha"], []),
    ("unread school", ["campus", "harvard in october"], ["Harvard"], []),
    ("later keeps it", ["campus", "yale", "later"], ["Kept"], []),
    ("help with a school named", ["campus", "can you help me visit yale on october 14"], ["Wed 14 Oct"], []),
    ("rambling voice", ["campus", "um so I want to visit yale with my daughter sometime around october 14 I guess"], ["Wed 14 Oct"], []),
]
RELOCATION = [
    ("bare keyword", ["relocation"], ["first* application", "first application"], []),
    ("relocate synonym", ["relocate"], ["first* application", "first application"], []),
    ("renewal path", ["relocation", "it's a renewal"], ["renewal", "Renewal", "economic resources"], []),
    ("first through to passport", ["relocation", "first", "me", "myself"], ["passport"], []),
    ("Spanish", ["relocation", "primera solicitud"], ["economic resources"], []),
    ("unsure at route", ["relocation", "not sure"], ["already living in Spain"], []),
    ("typo keyword", ["relocaton"], ["first", "EX-01", "relocation", "Relocation"], []),
    ("change of mind", ["relocation", "first", "actually it's a renewal"], ["Noted: a renewal"], []),
    ("start over → no", ["relocation", "first", "start over", P("so:no:")], ["Back to your EX-01"], []),
    ("start over → yes", ["relocation", "first", "reset", P("so:yes:")], ["first* application", "first application"], []),
    ("switch and back", ["relocation", "first", "campus", "relocation"], ["Back to your EX-01"], []),
    ("sasha and back", ["relocation", "first", "sasha", "relocation"], ["Back to your EX-01"], []),
    ("demo to consulate", ["relocation", "DEMO", "SIGNED", "UK"], ["Londres", "London"], []),
    ("US then a state", ["relocation", "DEMO", "SIGNED", "United States", "new york"], ["Nueva York", "New York"], []),
    ("later keeps it", ["relocation", "first", "later"], ["Kept"], []),
]
ESPANA = [
    ("bare keyword", ["españa"], ["EspañaMe"], []),
    ("typo keyword", ["espña"], ["EspañaMe"], []),
    ("salud direct", ["salud"], ["Health details are sensitive", "Is that OK"], []),
    ("health card path", ["españa", "1", "yes", "3"], ["DNI", "passport"], []),
    ("health card in Spanish", ["españa", "1", "sí", "quiero mi tarjeta sanitaria"], ["DNI", "passport"], []),
    ("Spanish doctor", ["salud", "sí", "2"], ["SERMAS"], []),
    ("a concept area", ["españa", "2"], ["Padrón", "padrón"], []),
    ("consent no", ["españa", "1", "no"], ["nothing kept", "Nothing"], []),
    ("public route", ["españa", "1", "yes", "2"], ["SERMAS"], []),
    ("find my centre with no form", ["españa", "find my centre"], ["no address to look up"], []),
    ("start over → yes", ["españa", "1", "start over", P("so:yes:")], ["EspañaMe"], []),
    ("switch and back", ["españa", "1", "relocation", "españa"], ["Back to your health", "EspañaMe", "Health details"], []),
    ("back to sasha", ["españa", "sasha"], ["Back to Sasha"], []),
    ("demo card to the form", ["españa", "1", "yes", "3", "DEMO", P("hx:ts:ok:")], ["What is the card for"], []),
    ("later at the photo", ["españa", "1", "yes", "3", "later"], ["Kept"], []),
]
BAD = ("Something went wrong", "Traceback", "the model was called", ": None", "{'", "connection issue")


def run_scenario(case, steps) -> Tuple[bool, List[str], List[str]]:
    """→ (passed, problems, the replies per step)."""
    replies, problems = [], []
    for st in steps:
        a, b = len(GW.SENDER.sent), len(GW.SENDER.contents)
        try:
            if isinstance(st, tuple):
                btn = next((pl for _, pl in reversed(GW.SENDER.contents[-1][1] if GW.SENDER.contents else []) if pl.startswith(st[1])), None)
                if not btn:
                    problems.append(f"no button {st[1]}…")
                    replies.append("")
                    continue
                case.say("", payload=btn)
            else:
                case.say(st)
        except AssertionError as e:
            problems.append(f"«{st}»: {str(e)[:60]}")
            replies.append("")
            continue
        r = "\n".join([s["body"] for s in GW.SENDER.sent[a:]] + [c for c, _ in GW.SENDER.contents[b:]])
        replies.append(r)
        if not r.strip():
            problems.append(f"«{st}»: no reply (dead end)")
        if any(x in r for x in BAD):
            problems.append(f"«{st}»: error text")
        if len(replies) >= 2 and r.strip() and r == replies[-2]:
            problems.append(f"«{st}»: the same reply again (loop)")
    return not problems, problems, replies


def sweep(cls, scenarios) -> List[Tuple[str, bool, List[str]]]:
    out = []
    for name, steps, expect, forbid in scenarios:
        case = cls("run")
        case.setUp()
        try:
            ok, problems, replies = run_scenario(case, steps)
            last = replies[-1] if replies else ""
            if expect and not any(e in last for e in expect):
                ok = False
                problems.append(f"expected one of {expect} — got «{last[:120]}»")
            for f in forbid:
                if any(f in r for r in replies):
                    ok = False
                    problems.append(f"forbidden «{f}»")
        finally:
            case.tearDown()
        out.append((name, ok, problems))
    return out


def classes():
    from tests import test_campusme_cr1 as TC, test_relocation_m3_cr1 as TR, test_tarjeta_cr30 as TT
    from tests import test_finder_cr35 as TF

    class Campus(TC.OnWhatsApp):
        def run(self):
            pass

    class Relocation(TR.Flow):
        def run(self):
            pass

    class Espana(TF.Base):
        def run(self):
            pass
    return Campus, Relocation, Espana


def main() -> int:
    Campus, Relocation, Espana = classes()
    total_fail = 0
    for label, cls, sc in (("campus", Campus, CAMPUS), ("relocate", Relocation, RELOCATION), ("españa", Espana, ESPANA)):
        res = sweep(cls, sc)
        n = sum(ok for _, ok, _ in res)
        print(f"\n== {label}: {n}/{len(res)} pass")
        for name, ok, probs in res:
            if not ok:
                total_fail += 1
                print(f"  ✗ {name}: " + " | ".join(probs))
    return total_fail


if __name__ == "__main__":
    import logging
    logging.disable(logging.CRITICAL)
    sys.exit(1 if main() else 0)
