"""Sasha 392 · Stage B re-apply: the CTO's two conversation doors read and write the ONE conversation record (agapi/s2_memory), never
the page's copy. Every CTO zip replaces app/api/conductor.py and app/api/voice_conductor.py and drops these lines.
Idempotent; REFUSES, loudly, if an anchor moved — never a silent loss.

    cd ~/Projects/sasha-travel && python3 backend/scripts/stage_b_one_record_392.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MARK = "Sasha 392 one record (Stage B)"
IMP = "from agapi import s2_memory as _MEM392  # Sasha 392 one record (Stage B): the conversation is the ONE record's, never the page's copy\n"

CONDUCTOR = [
    ("from app.services.chat_account import acting, own_session, signed_in\n",
     "from app.services.chat_account import acting, own_session, signed_in\n" + IMP),
    ("    result = await classify_intents(body.message, body.conversation_history, has_itinerary)",
     "    _who = await acting(request)\n"
     "    _hist = await _MEM392.door_history(_who, signed_in(_who), body.message, body.conversation_history)  # " + MARK + "\n"
     "    result = await classify_intents(body.message, _hist, has_itinerary)"),
    ("        message, payload, product_mode = body.message, body.payload, body.product_mode\n",
     "        message, payload, product_mode = body.message, body.payload, body.product_mode\n"
     "        history = await _MEM392.door_history(account, signed_in(account), body.message, body.conversation_history)  # " + MARK + "\n"),
    ("                                     conversation_history=list(body.conversation_history or []) + [",
     "                                     conversation_history=list(history) + [  # " + MARK),
    ("            _r = await _vt.turn(account, message, body.conversation_history, tap=_VS.session_of(request), venues_only=True)",
     "            _r = await _vt.turn(account, message, history, tap=_VS.session_of(request), venues_only=True)  # " + MARK),
    ("            conversation_history=body.conversation_history,\n            client_config=client_config,",
     "            conversation_history=history,  # " + MARK + "\n            client_config=client_config,"),
    ("        quick = list(result.get(\"quick_replies\") or [])",
     "        await _MEM392.door_said(account, signed_in(account), \"rest\", body.message, result)  # " + MARK + "\n"
     "        quick = list(result.get(\"quick_replies\") or [])"),
]
VOICE = [
    ("        account = await acting(request)\n",
     "        account = await acting(request)\n        " + IMP +
     "        history = await _MEM392.door_history(account, signed_in(account), transcript, history)  # " + MARK + "\n"),
    ("            result = await conduct(transcript, history, user_id=account, signed_in=signed_in(account))\n",
     "            result = await conduct(transcript, history, user_id=account, signed_in=signed_in(account))\n"
     "        await _MEM392.door_said(account, signed_in(account), \"voice\", transcript, result)  # " + MARK + "\n"),
]


def apply(rel: str, edits) -> None:
    p = ROOT / rel
    s = p.read_text()
    if MARK in s:
        print(f"{rel}: one record already present")
        return
    missing = [a[:70] for a, _ in edits if s.count(a) != 1]
    if missing:
        sys.exit(f"⛔ STOP: {rel}'s anchors changed in this CTO drop — the one conversation record was NOT re-applied: {missing}")
    for a, b in edits:
        s = s.replace(a, b, 1)
    p.write_text(s)
    print(f"{rel}: one record re-applied")


if __name__ == "__main__":
    apply("app/api/conductor.py", CONDUCTOR)
    apply("app/api/voice_conductor.py", VOICE)
