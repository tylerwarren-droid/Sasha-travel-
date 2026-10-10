"""CR 75 step 7 · THE ACCIDENT PLAYBOOK (EU 216 §7): one step at a time; never on until the step is answered.

  1 safety     "Is anyone hurt?" — yes or unsure → "Call 112 now" and NOTHING else until they say help is on the way (the emergency number
               quoted from an official source). Injuries also mean the hand-off line.
  2 duties     the duties at the scene, quoted from the country's official source — a country whose source isn't read at source (and checked)
               says so; nothing is shown from a search summary
  3 photos     a guided list, one shot at a time; each upload sealed under the person's own Keep key and recorded as hashed, timestamped evidence
  4 statement  the European Accident Statement, FACTS ONLY: date, time, place, the vehicles as the person gives them, their Keep items as
               MASKS. The circumstances boxes and the sketch are left for the person and the other driver; Sasha never ticks a box that bears
               on fault, and never signs. The source's own advice on signing, quoted.
  5 clocks     three deadlines, each quoted: the rental company's (its terms), the card insurer's (the card's terms), the country's (its law);
               a clock no source gives is said missing
  6 notify     the rental company, on the person's yes (cards.accident_notify), then into the claim flow for the card insurer (its own yes)
Hand-off — injuries, disputed fault, police charges, any claim against the person: "This needs a lawyer or your insurer's legal team.\""""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

STEPS = ("safety", "duties", "photos", "statement", "clocks", "notify", "claim")
SHOTS = ("your_car_front", "your_car_back", "your_car_left", "your_car_right", "the_damage_close_up", "the_other_car_and_its_plate",
         "your_rental_cars_plate", "the_road_and_signs", "the_other_drivers_licence_and_insurance")
SHOT_SAY = {"your_car_front": "Your car from the front", "your_car_back": "Your car from behind", "your_car_left": "Your car's left side",
            "your_car_right": "Your car's right side", "the_damage_close_up": "The damage, close up",
            "the_other_car_and_its_plate": "The other car, with its number plate", "your_rental_cars_plate": "Your rental car's number plate",
            "the_road_and_signs": "The road and any signs", "the_other_drivers_licence_and_insurance": "The other driver's licence and insurance papers — only with their agreement"}
HANDOFF = "This needs a lawyer or your insurer's legal team. I can find one for you, and I'll keep doing only the paperwork."
HANDOFF_FLAGS = ("injuries", "fault_disputed", "police_charges", "claim_against_me")
STATEMENT_NAME = {"ES": "Declaración Amistosa de Accidente", "FR": "constat amiable", "IT": "Constatazione Amichevole di Incidente (CAI)",
                  "PT": "Declaração Amigável de Acidente Automóvel", "DE": "Europäischer Unfallbericht"}
NEVER = ("circumstances boxes (1–17)", "the sketch", "the signature")
COUNTRY = {"ES": "Spain", "FR": "France", "DE": "Germany", "IT": "Italy", "PT": "Portugal", "GB": "the UK", "IE": "Ireland", "NL": "the Netherlands"}


def _why(note: Optional[str]) -> str:
    """'not read at source yet' → said once, plainly; any other note in brackets."""
    if not note or note == "not read at source yet":
        return "aren't read at source yet"
    return f"can't be used yet ({note})"


def _q(c: dict) -> dict:
    return {"claim_id": c["id"], "quote": c["quote"], "source_url": c["source_url"], "read_at": c["read_at"][:10]}


def _get(cl: List[dict], benefit: str, field: str) -> List[dict]:
    return [c for c in cl if c["benefit"] == benefit and c["field"].split("@")[0] == field]


def safety(answer: Optional[str], emergency: Optional[dict]) -> Dict[str, Any]:
    """→ {say, done, call?}. Nothing else is offered until this is answered and, if anyone may be hurt, help is on the way."""
    num = emergency["value"] if emergency else "112"
    call = {"number": num, **({"source": _q(emergency)} if emergency else {})}
    if answer in (None, ""):
        return {"say": "Is anyone hurt?", "choices": ["no", "yes", "not sure"], "done": False}
    if answer in ("yes", "not sure", "unsure"):
        return {"say": f"Call {num} now.", "call": call, "choices": ["help is on the way"], "done": False, **({"handoff": HANDOFF} if answer == "yes" else {})}
    if answer == "help is on the way":
        return {"say": "Good. If it's safe: hazard lights on, the vest on, the warning triangle out, everyone off the road.", "done": True, "call": call}
    if answer == "no":
        return {"say": "OK. If it's safe: hazard lights on, the vest on, the warning triangle out, everyone off the road.", "done": True}
    return {"say": "Is anyone hurt?", "choices": ["no", "yes", "not sure"], "done": False}


def duties(country: str, law: Optional[List[dict]], law_note: Optional[str]) -> Dict[str, Any]:
    if law is None:
        return {"say": f"The official rules for {COUNTRY.get(country, country)} {_why(law_note)}, so I won't quote them. Stay at the scene, keep "
                       "everyone safe, and exchange details with the other driver.", "quotes": [], "read_at_source": False}
    lines = []
    for f, head in (("safety_steps", "Make the scene safe"), ("scene_duties", "Your duties at the scene"), ("police_when", "When to call the police")):
        for c in _get(law, "accident_rules", f):
            v = c["value"]
            lines.append({"say": f"{head}: " + ("; ".join(v) if isinstance(v, list) else str(v)) + ".", "quotes": [_q(c)]})
    return {"say": "What the official rules say:" if lines else f"The official source for {country} I've read doesn't list the duties at the scene.",
            "lines": lines, "read_at_source": True}


def photo_list(taken: List[str]) -> Dict[str, Any]:
    left = [s for s in SHOTS if s not in taken]
    return {"say": (f"Next: {SHOT_SAY[left[0]]}." if left else "That's every photo on the list."), "shots": [{"shot": s, "say": SHOT_SAY[s], "taken": s in taken}
            for s in SHOTS], "next": left[0] if left else None}


def statement(country: str, facts: Dict[str, Any], keep_masks: List[str], law: Optional[List[dict]]) -> Dict[str, Any]:
    """The European Accident Statement, FACTS ONLY. Never a fault box, never a signature."""
    name = next((c["value"] for c in _get(law or [], "accident_rules", "statement_name")), None) or STATEMENT_NAME.get(country, "European Accident Statement")
    advice = [{"say": "Its own advice on the form:", "quotes": [_q(c)]} for c in _get(law or [], "accident_rules", "statement_advice")]
    return {"form": name, "facts": {"date": facts.get("date"), "time": facts.get("time"), "place": facts.get("place"),
                                    "injuries": facts.get("injuries", "none, as you said"), "your_vehicle": facts.get("your_vehicle") or {},
                                    "your_insurer": facts.get("your_insurer"), "your_details_from_keep": keep_masks,
                                    "witnesses": facts.get("witnesses") or []},
            "left_for_you": list(NEVER),
            "say": ("Here's the statement with the facts filled in. The circumstances boxes and the sketch are yours to fill with the other driver. "
                    "Don't sign anything you disagree with — and I never sign."), "advice": advice}


def clocks(at: datetime, rental: Optional[List[dict]], rental_note: Optional[str], card_claims: Optional[List[dict]], card_name: Optional[str],
           law: Optional[List[dict]], country: str, law_note: Optional[str]) -> List[Dict[str, Any]]:
    out = []
    r = next(iter(_get(rental or [], "rental_terms", "accident_report_deadline_hours")), None)
    if r:
        out.append({"who": "the rental company", "due": (at + timedelta(hours=int(r["value"]))).strftime("%Y-%m-%d %H:%M"),
                    "say": f"Report it to the rental company within {r['value']} hours.", "quotes": [_q(r)]})
    else:
        out.append({"who": "the rental company", "due": None, "say": "The rental company's deadline: " + (rental_note or "its terms I've read don't give one") + ".", "quotes": []})
    c = None
    for cand in (card_claims or []):
        if cand["benefit"] == "claims" and cand["field"] in ("notice_deadline_days@car_rental", "notice_deadline_days"):
            c = cand if (c is None or cand["field"].endswith("@car_rental")) else c
    if c:
        out.append({"who": f"your card's insurer ({card_name})", "due": (at + timedelta(days=int(c["value"]))).strftime("%Y-%m-%d"),
                    "say": f"Notify your card's claims administrator within {c['value']} days.", "quotes": [_q(c)]})
    else:
        out.append({"who": "your card's insurer", "due": None, "say": "Your card's terms I've read don't give a notice deadline: tell them now.", "quotes": []})
    if law is None:
        out.append({"who": country, "due": None, "say": f"{COUNTRY.get(country, country)}'s own deadline: its official rules {_why(law_note)} — not shown.", "quotes": []})
    else:
        d = next(iter(_get(law, "accident_rules", "notice_deadline_days")), None)
        h = next(iter(_get(law, "accident_rules", "notice_deadline_hours")), None)
        if d or h:
            x = d or h
            due = at + (timedelta(days=int(x["value"])) if d else timedelta(hours=int(x["value"])))
            out.append({"who": f"the law in {country}", "due": due.strftime("%Y-%m-%d"), "quotes": [_q(x)],
                        "say": f"The law in {COUNTRY.get(country, country)}: tell the insurer within {x['value']} {'days' if d else 'hours'}."})
        else:
            out.append({"who": f"the law in {country}", "due": None, "say": f"The official source I've read for {COUNTRY.get(country, country)} gives no deadline.", "quotes": []})
    return out
