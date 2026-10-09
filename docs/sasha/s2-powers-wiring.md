# CR 60 · Wiring S2's first powers into Sasha's agent — the merge note

**Not applied.** This is for the Sasha tab, to merge on a founder ticket.
- **Branch:** `cr/s2-powers`, from main `9764359`.
- **What's already there:** the shared logic (`backend/agapi/powers.py`, the same bytes as the AgAPI sandbox runs, sha256 `2a0b1f9b…`), the two tool adapters (`backend/agapi/s2_tools.py`), their tests (`backend/tests/test_s2_powers.py`, 7) and the shared vectors (`backend/tests/fixtures/agapi_powers_vectors.json`).
- **What isn't changed:** nothing the agent imports today. `sasha.py`, `v0.py` and the agent loop are untouched.

**Size:** 3 files.
- `agapi/v0.py`: 2 lines.
- `app/agent/sasha.py`: 4 small hunks, about 14 lines.
- `tests/test_agapi_guards.py`: 0 lines; its renderer check passes once hunk 2 is in.

## The hunks

**1 · Register the tools.** In `agapi/v0.py`, right after `BY_NAME = {t["name"]: t for t in TOOLS}` (line 887):
```python
from agapi import s2_tools as _S2   # CR 60 · email from Sasha's address + calendar (agapi/powers.py, shared with the AgAPI sandbox)
TOOLS += _S2.tools(); BY_NAME.update({t["name"]: t for t in _S2.tools()})
```

**2 · The renderers.** In `app/agent/sasha.py`, beside `RENDER` (line 105):
```python
RENDER.update({"send_email": "read_back", "add_to_calendar": "inline"})   # CR 60
```
- `send_email`'s first call returns `read_back` (the exact message): the UI's existing read-back card shows it.
- `add_to_calendar` is inline: her words carry the links. A dedicated "calendar" card is optional later and needs a new `KINDS` entry.

**3 · The yes comes from the person, never the model.** Line 571 becomes:
```python
            if u.name in ("book", "book_venue", "cancel_venue", "send_email"):   # CR 60: send_email's yes is the real words too
```
`send_email` is already idempotent (Austen): the loop's idempotency-key line covers it unchanged.

**4 · The .ics file behind "Apple / any calendar".** Add to `app/agent/sasha.py`, beside `@router.post("/turn")`. The router is already mounted at `/api/agent`.
```python
@router.get("/ics/{token}.ics")   # CR 60 · key-less by an unguessable token; nothing personal beyond the event
async def agent_ics(token: str):
    from fastapi.responses import Response
    from agapi import s2_tools as S2
    f = S2.ICS.get(hashlib.sha256(token.encode()).hexdigest())
    if not f:
        return JSONResponse({"ok": False}, status_code=404)
    return Response(f["ics"], media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="sasha.ics"'})
```
`S2.ICS` is in memory, so a deploy clears the links. They're also returned inline as `ics`, so the person can re-ask. If Tyler wants links to survive deploys, a table is a follow-up.

**5 · Persona** (one line in `sasha-persona.md`'s abilities, so she offers it):
> "I can email someone for you from my own address (never yours): I'll read you the exact message and send it only after your yes. And I can put any confirmed booking in your calendar."

## What this does NOT change
- **The CR 54 skill scoping (`cr/campusme-skill`).** If it's merged, `send_email` and `add_to_calendar` are Sasha's own tools: they stay outside every skill's list.
- **CR 56 gap 1 (the yes).** `s2_tools.strict_yes` already vetoes questions for email. The same veto should replace `v0.explicit_yes` everywhere: a separate ticket.
- **Live email.** In TEST mode emails are captured (`S2.OUTBOX`), never sent. Real sending needs **`SASHA_S2_EMAIL_LIVE=1` and a live context**, by Tyler's decision. It then uses the S-36 rung's Resend send (`emailing.send`), whose answer is read: "sent" means accepted for delivery.

## Checks after the merge
- `python -m unittest tests.test_s2_powers tests.test_agapi_guards` passes. Run hunk 2 before the guards test.
- In /next, try "email Marta our flight times":
  1. She reads back the exact message.
  2. "Yes — what will it say?" is refused.
  3. "Yes, send it." sends it (captured in test).
- "put my dinner in my calendar" returns three links.

## CR 61 follow-up (after Sasha 216's merge)
- **Merged state.** This branch now contains `sasha/216` (fa36619). Sasha 216 already did Tyler's two CR 61 decisions in its own way: live email for the founder and `SASHA_REAL_CONTACT_ACCOUNTS` (Jon), with `SASHA_S2_EMAIL_LIVE=0` as the kill switch; and calendar links that survive deploys by carrying the signed `.ics` inside the link (`ics_token` / `ics_from_token`), with no table. CR 61's table draft (fdc5312) was dropped in favour of the signed links.
- **One addition: honesty for a captured email.** A guest's email (not the founder's or Jon's) used to come back as `status: "sent"` with "Accepted for delivery (test mode…)". It now comes back as `status: "not_sent"`, `outcome.kind: "NOT_SENT"`, "Not sent: real email isn't open on this account yet. Nothing left Sasha." So she never says "sent" for a message that didn't leave.
- **Tests.** `tests/test_s2_powers.py` LiveEmailAllowList covers who may send (founder, Jon, case-insensitive; nobody else; nobody with `=0`). It also checks that the founder and Jon really send, once, and that a guest is told "not sent".
