# The Keep v1 — wiring note (CR 63)

Branch `cr/s2-keep`, built on `cr/s2-powers-2` (CR 62), because every Keep use writes an Activity row there. **Merge `cr/s2-powers-2` first.** Nothing here is wired yet, and the branch passes the full suite on its own.

## What it is
The person's numbers and codes, in three tiers. The logic is `backend/agapi/keep.py`, the same module the AgAPI sandbox's `keep.*` runs, with the same frozen vectors (`tests/fixtures/keep_vectors.json`).

| Tier | What | How it's used |
|---|---|---|
| free | preferences, loyalty / frequent-flyer numbers, home address | filled into a booking, no extra yes |
| yes | passport, DNI/NIE, Global Entry/PreCheck, visa/residence, insurance policy, health card | filled only when the read-back the person **heard** named it ("I'll use your saved Passport ES ••••456 for this booking.") and they said yes |
| read_back | booking references, door / Wi-Fi codes, eSIM | shown only on the person's own `/keep` screen; never filled anywhere |
| never | card numbers (Apple Pay only), one-time / 2FA codes, passwords (not in v1) | refused, and the refusal never repeats the value |

**The model never sees a value.**
- `keep_list` returns masks only.
- `keep_use` binds an item to the next booking, or puts it on the person's screen. Asking it for `raw`, `value` or `reveal` is refused with `never_raw`.
- Values come in only from the person's own `/keep` form, never through the chat. A passport or ID number typed in the chat is withheld by `chat_guard`.

**Envelope.**
- Each account has one data key, wrapped by **Google Cloud KMS**: the KMS S-78's vault already uses (`booking_signer/vault/kms.py`, `SASHA_VAULT_KMS_KEY`).
- Each value is AES-256-GCM under that key, with a fresh nonce, bound to the account, item and type.
- The database holds only ciphertext, a mask and a *keyed* fingerprint. Never a value, never a plain hash.
- Deleting everything drops the wrapped key, which shreds every value at once.
- No KMS, or 037 not applied: the Keep is **closed** and says so. It never falls back to memory.

## Files on the branch
| File | Change |
|---|---|
| `backend/agapi/keep.py` | **new**, shared with the sandbox (git blob identical to `cr/agapi-api`) |
| `backend/agapi/powers.py` | four Activity lines for the Keep (identical to `cr/agapi-api`) |
| `backend/agapi/s2_keep.py` | **new**: store, envelope, `put/list_/show/delete`, `bind → lines → approve → fill`, `chat_guard`, the two tools, the `/keep` routes |
| `backend/agapi/activity.py` | Keep rows in the Activity view |
| `backend/booking_signer/sql/037_keep.sql` | **new**: `keep_keys`, `keep_items`, `keep_fills`; widens 036's `s2_acts` kinds. Apply **after the deploy, after 036.** |
| `frontend/app/keep/page.tsx` + `frontend/app/api/sasha-agent/keep/**` | **new**: the `/keep` screen (save, masks, Show for read-back items, delete one, delete everything after typing DELETE) and its pass-through |
| `frontend/scripts/check-outcome-surfaces.mjs` | `/keep` added on its own line |
| `backend/tests/test_keep_s63.py` | 15 tests, including the routes and Postgres (the tables are scanned: the mask is there, the value and its plain hash aren't) |

## The wiring — 5 files, 19 lines

**1 · `backend/agapi/v0.py`**: register the tools, mark `keep_list` as a read, name the item in the read-back, approve on the yes.
```python
# after BY_NAME.update(...) at the CR 60 / CR 62 registrations:
from agapi import s2_keep as _KEEP   # noqa: E402 · CR 63 · the Keep (masks only)
TOOLS += _KEEP.tools()
BY_NAME.update({t["name"]: t for t in TOOLS})
# READS: + "keep_list"
# hold_booking, directly above `prev = _HELD.get(ctx.account)   # Sasha 210`:
    res["read_back"] += await _KEEP.lines(ctx.account)   # CR 63 · a bound passport is NAMED in what she reads out
# book, directly above `sent = str(got.get("phone") or "")...`:
    await _KEEP.approve(ctx.account, held["result"]["read_back"], said, got["session_id"])   # CR 63 · this yes, this payment
```
`keep_use` already drops a reused read-back (`_HELD`) when it binds a document, so `hold_booking` reads it out again.

**2 · `backend/booking_signer/basket_book.py`, `book_paid()`**: one `async with` around the loop of orders, so a round trip's two flights both carry it:
```python
    from agapi import s2_keep as KEEP   # CR 63 · the Keep's approved items for THIS payment: opened here, dropped after
    async with KEEP.fill(account, sid) as kept:
        for r in [r for r in rows if r["state"] == "pending_payment"]:
            ...                                  # unchanged, except the two T.order calls gain:  documents=kept.duffel()
            # and after `if "why" in o: ... continue` / before T.RECORD:
            kept.result(o.get("booking_reference"), "why" not in o)
```

**3 · `backend/booking_signer/travel.py`, `order()`**: a `documents` parameter, given to the account holder's passenger:
```python
async def order(c, name, email, phone, people=None, documents: Optional[list] = None):
    ...  # after the placeholder `pax = [...]` block:
    if documents and pax:   # CR 63 · the Keep's identity documents (opened just for this order) → the account holder's passenger
        pax[next((k for k, p in enumerate(people or []) if p.get("is_account_holder")), 0) % len(pax)]["identity_documents"] = documents
```

**4 · `backend/app/agent/sasha.py`**: renderers, the routes, and **the input guard `/next` never had**:
```python
RENDER.update({"keep_list": "inline", "keep_use": "inline"})   # CR 63
router.include_router(_KEEP_router)   # with: from agapi.s2_keep import router as _KEEP_router  → /api/agent/keep…
# agent_turn, right after `if not message: return ... 400`:
    from agapi import s2_keep as _KEEP   # CR 63 · S-78's guard + the Keep's, BEFORE the model (found: /next had no input guard)
    _held = _KEEP.chat_guard(message)
    if _held:
        return StreamingResponse(iter([f"data: {json.dumps({'type': 'say', 'text': _held})}\n\n",
                                       f"data: {json.dumps({'type': 'done', 'text': _held, 'guard': ['input_guard']})}\n\n"]),
                                 media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
    body["history"] = _KEEP.clean_history(body.get("history") or [])
```

**5 · Persona** (two lines):
> "Your passport, ID and loyalty numbers can live in your Keep (/keep). I never see them — only something like 'Passport ES ••••456' — and I'll use one only where it's needed, after your yes."
> "Never ask for a document number in the chat; if they offer one, send them to /keep."

Then regenerate the contract doc: `cd backend && python -m scripts.agapi_doc`.

**Proven.** CR 63 applied exactly these edits on a throwaway branch. The full suite passed (1654), including `tests/test_keep_wired_s63.py`. That file is on this branch and **skipped until the wiring is in**, then it runs by itself. It checks four things:
- `travel.order` puts the passport on the account holder's passenger;
- `book_paid` fills both flights of a round trip, with one Activity row ("REF1, REF2");
- `/next` answers a typed passport or password with the fixed reply, and the model is never called;
- `hold_booking` names the bound passport in what she reads out.

That run also caught a contract slip: every Austen tool takes an idempotency key, and `keep_use` now does.

## After the merge (the founder)
1. Deploy, apply **036** (CR 62) if it isn't applied yet, then **037**. Until 037 runs, the Keep says it's closed.
2. `SASHA_VAULT_KMS_KEY` and `SASHA_VAULT_GCP_SA_JSON` are already S-78's. If they're set on Railway, the Keep uses them; if not, it stays closed.
3. Check:
   - On `/keep`: save a passport and see "Passport ES ••••456".
   - In `/next`: "book my flight", then "use my passport". The read-back names it. "Yes, book it." Pay (test).
   - `/activity` shows "Used from your Keep for a booking" with Proof.
   - Typing "my passport is …" in `/next` gets the fixed reply, and the model never sees it.

## For Tyler to decide
- **Duffel LIVE + real passports.** In TEST, Duffel takes the document and keeps nothing. A live order sends it to the airline, which is the point, but it's a new processor relationship to confirm under the DPA.
- **Typed numbers in the chat** are withheld for passports and IDs (`chat_guard`), but loyalty numbers typed in the chat still reach the model. Tier free, so it's low risk; say if you want those withheld too.
