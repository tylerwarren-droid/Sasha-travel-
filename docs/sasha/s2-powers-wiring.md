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
@router.get("/ics/{token}.ics")   # CR 60/61 · key-less by an unguessable token; nothing personal beyond the event
async def agent_ics(token: str):
    from fastapi.responses import Response
    from agapi import s2_tools as S2
    text = await S2.ics_for(token)          # CR 61: the sasha_calendar_links table, else memory; None when unknown or expired
    if not text:
        return JSONResponse({"ok": False}, status_code=404)
    return Response(text, media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="sasha.ics"'})
```
**CR 61 · links survive deploys.** Apply `booking_signer/sql/036_calendar_links.sql` in Supabase *after* this deploys (the founder runs it; it only adds a table: token sha256, account, .ics, event sha256, expiry = 30 days after the event). Until it runs, links live in memory as in CR 60 and the code says so in the log; nothing breaks. The token itself is never stored.

**5 · Persona** (one line in `sasha-persona.md`'s abilities, so she offers it):
> "I can email someone for you from my own address (never yours): I'll read you the exact message and send it only after your yes. And I can put any confirmed booking in your calendar."

## What this does NOT change
- **The CR 54 skill scoping (`cr/campusme-skill`).** If it's merged, `send_email` and `add_to_calendar` are Sasha's own tools: they stay outside every skill's list.
- **CR 56 gap 1 (the yes).** `s2_tools.strict_yes` already vetoes questions for email. The same veto should replace `v0.explicit_yes` everywhere: a separate ticket.
- **Live email (CR 61, Tyler's answers).** From `SASHA_EMAIL_FROM` (a separate mail subdomain later). Real sending needs **`SASHA_S2_EMAIL_LIVE=1` on Railway AND the founder's account (`FOUNDER_ACCOUNT_ID`) or an allow-listed one**. The allow-list is `SASHA_S2_EMAIL_ACCOUNTS` if set, else the existing `SASHA_REAL_CONTACT_ACCOUNTS` (Jon's account). Everyone else: captured in `S2.OUTBOX`, never sent, and the tool returns `status: "not_sent"` with "Not sent: real email isn't open on this account yet", so she never says "sent" for a message that didn't leave. A real send uses the S-36 rung's Resend send (`emailing.send`), whose answer is read: "sent" means accepted for delivery.

## Checks after the merge
- `python -m unittest tests.test_s2_powers tests.test_agapi_guards` passes. Run hunk 2 before the guards test.
- In /next, try "email Marta our flight times":
  1. She reads back the exact message.
  2. "Yes — what will it say?" is refused.
  3. "Yes, send it." sends it from the founder's account (real, once `SASHA_S2_EMAIL_LIVE=1`); on a guest account she says it was NOT sent.
- "Put my table in my calendar", then redeploy: the Apple/.ics link still opens (after 036 is applied).
- "put my dinner in my calendar" returns three links.
