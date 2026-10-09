# S2 powers 2 — wiring note (CR 62)

Branch `cr/s2-powers-2`, from main @ 492ad2b (Sasha 216, with CR 61's `not_sent`). Two new tools: **`send_whatsapp`** and
**`get_activity`**. They use the same logic as the AgAPI sandbox's `messages.send_whatsapp` and `activity.list`
(`backend/agapi/powers.py`, the same byte-for-byte module). Nothing is wired yet; the branch passes the full suite on its own.

## What's on the branch

| File | What |
|---|---|
| `backend/agapi/powers.py` | Additions shared with the sandbox: `whatsapp_message`, `whatsapp_read_back`, `window_open`, the first-contact template `ON_BEHALF` (its words go to Meta), and the activity lines `ACTIVITY_LINES` / `activity_entry`. |
| `backend/agapi/s2_whatsapp.py` | The `send_whatsapp` tool and the inbound hook `on_contact_message`. |
| `backend/agapi/activity.py` | `collect()` (the view, from Pacioli's records), the `get_activity` tool, and the route `GET /api/agent/activity`. |
| `backend/agapi/s2_records.py` | S2's own records: emails, WhatsApps and calendar adds with their proof, the contacts and their replies. Postgres after 036; in memory until then. |
| `backend/agapi/s2_tools.py` | `send_email` and `add_to_calendar` now also write their Activity row. Nothing else changed. |
| `backend/booking_signer/sql/036_s2_activity_whatsapp.sql` | Three tables, adds only. Apply **after** the deploy. |
| `frontend/app/activity/page.tsx` + `frontend/app/api/sasha-agent/activity/route.ts` | The phone-first `/activity` screen and its pass-through (founder or a signed-in guest, as for `/next`). |
| `backend/tests/test_s2_cr62.py` | 12 tests, including Postgres. The shared vectors are in `tests/fixtures/agapi_powers_vectors.json` (the sandbox's file). |

## The wiring — 4 places, 11 lines

**1 · `backend/agapi/v0.py`** (after `TOOLS += _S2.tools()`; and the two sets):
```python
from agapi import s2_whatsapp as _WA, activity as _ACT   # noqa: E402 · CR 62 · WhatsApp to someone named + the Activity view
TOOLS += _WA.tools() + _ACT.tools()
BY_NAME.update({t["name"]: t for t in TOOLS})
ACTS = {"book", "book_venue", "cancel_venue", "send_email", "send_whatsapp"}     # + send_whatsapp: claimed once, durably
READS = {..., "add_to_calendar", "get_activity"}                                    # + get_activity
```

**2 · `backend/app/agent/sasha.py`** (four one-line edits):
```python
RENDER.update({"send_email": "read_back", "add_to_calendar": "inline", "send_whatsapp": "read_back", "get_activity": "inline"})
**({"what": "email" if tool == "send_email" else "whatsapp", "live": bool(res.get("live"))} if tool in ("send_email", "send_whatsapp") else {}),
if u.name in ("book", "book_venue", "cancel_venue", "send_email", "send_whatsapp"):   # the REAL words of this turn, never the model's
from agapi.activity import router as _activity_router; router.include_router(_activity_router)   # CR 62 · GET /api/agent/activity
```
The third line matters most. Without it, `approval.said` is empty, so `send_whatsapp` never sends. That fails safe, but it's useless.

**3 · `backend/booking_signer/guest_whatsapp.py`, in `dispatch()`**, directly above `from . import invitations as IV   # S-80 · Jon opting in`
(that is, after the `if ch:` block, so a linked guest is never affected):
```python
    from agapi import s2_whatsapp as S2WA   # CR 62 · a reply from someone Sasha wrote to FOR a person: kept, never answered by the model
    kept = await S2WA.on_contact_message(sender, p.get("Body") or "")
    if kept is not None:
        return _twiml_message(kept) if kept else ""
```
Without it, a recipient's reply would create a guest account for them (Sasha 153), and their window would never open.

**4 · Persona** (`sasha-persona.md`, abilities; two lines):
> "I can WhatsApp someone for you from my own number: I'll read you the exact message and send it only after your yes. If they haven't written to me before, WhatsApp only lets me send a short approved note asking if they'd like your message — yours goes once they reply."
> "Asked what she's done ('what have you done for me today?'), she calls `get_activity` and says only what it lists; the full list with proof is on the Activity screen."

Then regenerate the contract doc: `cd backend && python -m scripts.agapi_doc` (`docs/agapi/api-v0.md` lists every tool; the guards test fails until it's run).

**Proven:** CR 62 applied exactly these edits on a throwaway branch. The full suite passed (1634), `GET /api/agent/activity` answered 403 when not signed in (mounted once, at the right path), and the hook was in `dispatch`.

Optional: a link to `/activity` on `/you` (one line, `<a href="/activity">Everything Sasha did for you</a>`).

## Rules held in code (not by her words)
- **Free text goes only inside WhatsApp's 24-hour window**, meaning the recipient wrote to Sasha in the last 24 hours. Otherwise only the approved template goes, and it asks them first. The person's note waits for the reply and gets its own yes.
- **Live only for the founder and Jon** (`s2_tools.live_for`: `FOUNDER_ACCOUNT_ID` + `SASHA_REAL_CONTACT_ACCOUNTS`; `SASHA_S2_EMAIL_LIVE=0` stops both email and WhatsApp). Everyone else: captured, `status: "not_sent"`, said as not sent, and shown in Activity as ✕ "WhatsApp not sent".
- **Without an approved template** (`SASHA_WA_ONBEHALF_SID` empty), the founder's first contact returns `not_possible_yet`, with a plain sentence offering email instead.
- **STOP is final**, for every account that wrote to that number. A later "start" doesn't undo it.
- **Replies are their words.** They are kept (`s2_wa_replies`) and listed as "They replied on WhatsApp". The text itself is never in the Activity line, and the model never answers it. The fixed reply is "Thank you — I've passed your reply on to {name}."
- **Activity lines are fixed wording** (`powers.ACTIVITY_LINES`). A record that couldn't be read is named (`unavailable`), never left out silently.

## After the merge (Tyler / the founder)
1. Deploy, then apply `036_s2_activity_whatsapp.sql` in Supabase. Until then the records are in memory, the log says so once, and nothing breaks.
2. **Tyler decides:** submit the first-contact template to Meta (UTILITY, English) with exactly these words:
   `Hi {{1}}, this is Sasha, an assistant writing for {{2}}. {{2}} asked me to send you a message here. Reply YES to receive it, or STOP and I won't write again.`
   Once approved, put its Twilio ContentSid in `SASHA_WA_ONBEHALF_SID` on Railway. Until then the founder's first contact is "not possible yet".
3. Checks:
   - `python -m unittest tests.test_s2_cr62 tests.test_s2_powers tests.test_s2_216 tests.test_agapi_guards` passes. After wiring step 2, the guards test checks the renderers.
   - In /next on a guest account: "WhatsApp Marta +44 7700 900123 that I'm running late". She says WhatsApp needs a first message, reads it back, and on "Yes, send it." says it was NOT sent.
   - Open /activity: ✕ WhatsApp not sent, with Proof.
