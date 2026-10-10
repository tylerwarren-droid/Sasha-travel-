# S2 on AgAPI: the wiring

*CR 71 · branch `cr/s2-via-agapi` (from main `6899468`), for the Sasha tab to merge. Not on main.*

/s2 can ask AgAPI live (`agapi-live`) instead of Sasha's own engine, one step at a time. A single variable,
`SASHA_S2_VIA_AGAPI`, controls it, and it is read **only** in /s2's own tool selection.

**/next and S1 never read it.** In every mode they are byte-identical to today and make zero AgAPI calls. Tests prove both.

## What changes in the code

### 1 · `backend/agapi/via_agapi.py` (new)

- **`mode()`** reads `SASHA_S2_VIA_AGAPI`. Anything unrecognised counts as `0`.
- **`runner(base)`** returns the tool runner for an /s2 turn. In mode `0` it is `base` (`agapi.v0.call`) itself, unwrapped.
- **`GUEST_TOKEN`** carries this guest's own sign-in token, which goes with every AgAPI call as `X-Sasha-Guest-Token`.
- **`SHADOW_LOG`** keeps the last 200 comparisons. They hold names, flight numbers and prices only, never guest data.

### 2 · `backend/app/agent/sasha.py` (8 lines)

**In `turn()`, before /s2's block (around line 496):**
```python
run = API.call        # CR 71 · how a tool runs: agapi.v0.call, as always — /s2's block below is the ONLY place that changes it
```

**Inside `if surface == "s2":`, after `tools = [t for t in tools if t["name"] in S2.S2_TOOLS]`:**
```python
from agapi import via_agapi as VIA   # CR 71 · SASHA_S2_VIA_AGAPI (0 · shadow · reads · 1), read here and nowhere else
run = VIA.runner(API.call)
```

**In the tool loop (around line 635):** `r = await API.call(ctx, u.name, args)` becomes `r = await run(ctx, u.name, args)`.

**In `agent_turn()`, after `surface = …`:**
```python
guest_token = request.headers.get("authorization", "").partition(" ")[2].strip() if surface == "s2" else None   # CR 71 · /s2 only
```

**First thing in `events()`:**
```python
if guest_token:   # CR 71 · this guest's own token goes with S2's AgAPI calls (via_agapi); /next never sets it
    from agapi import via_agapi as VIA
    VIA.GUEST_TOKEN.set(guest_token)
```

### 3 · `backend/tests/test_s2_via_agapi.py` (new, 11 tests)

- **S1:** the fingerprint (a scripted S1 conversation with a real tool call) is byte-identical in modes `0`, `shadow`, `reads`, `1`
  and an unrecognised value, with zero AgAPI calls.
- **/next:** in every mode, no token is set and nothing is read.
- **Placement:** the switch is read only inside /s2's block.
- **S2 modes:** each of `0`, `shadow`, `reads` and `1` is tested for what it does.
- **The client:** the guest's token and the key go with each call.

A deliberate break was checked: putting the runner in the shared path makes the S1 fingerprint test fail.

## The modes

| Mode | What /s2 does |
|---|---|
| `0` (default) | Exactly as today: Sasha's own engine, no AgAPI call. |
| `shadow` | Sasha's own engine answers, shown and done as today. AgAPI is asked the same **read** question alongside (`search_flights` → `travel.find_flights`, `search_venues` → `venues.find_venues`). The two answers are compared and the difference is logged (`[s2-via-agapi] {…}` in Railway's logs, plus `SHADOW_LOG`). Nothing from AgAPI is shown or done, and an AgAPI failure changes nothing. |
| `reads` | `search_flights` is answered by AgAPI: the same Duffel offers, by their ids. They are fed into Sasha's basket exactly as her own search does, so `choose_offer` and `book` work unchanged. If AgAPI has nothing (it doesn't retry the nearby days the way Sasha's search does), Sasha's engine answers. `search_venues` stays on Sasha's engine and keeps being compared. |
| `1` | Today, the same as `reads`. Acts move to AgAPI only after the decision below. |

**Flip back:** set `SASHA_S2_VIA_AGAPI=0`, or delete it, on Sasha's Railway. The next tool call is Sasha's own again, with no
deploy and no data change.

## Order: merge, then switch on

1. **AgAPI** (`cr/agapi-api` @ `18070d2`) is already deployed on `agapi-live`. It accepts `X-Sasha-Guest-Token` only from the
   sasha product's live key, and the venue ladder then calls Sasha's routes as that guest.
2. **Merge `cr/s2-via-agapi` into main** through the Sasha tab's normal gate. With the variable unset, the merge changes
   nothing: mode `0`.
   - If Sasha 224 (the Keep on /s2) is merged first, the only overlap is /s2's block in `turn()`. Keep both additions in it.
3. **Railway (Sasha's service), Tyler pastes:**
   - `SASHA_AGAPI_KEY` = the `sasha` live key (Keychain "AgAPI live key" / "sasha");
   - `SASHA_AGAPI_URL` = `https://agapi-live-production.up.railway.app`.
4. **`SASHA_S2_VIA_AGAPI=shadow`.** Use /s2 normally for a day, then read the comparisons:
   `railway logs --service Sasha-travel- | grep s2-via-agapi`.
5. **`reads`**, once the flights compare the same, or the differences are understood. Watch AgAPI's `/metrics` (Falguni's key).
6. **`1`**, after the decision below.

## Open before `1`

1. **Acts need an approval AgAPI accepts.**
   - S2's yes is said in the chat (`approval: {"said": …}`). AgAPI live accepts an approval only from its own approval link,
     opened on the guest's own phone.
   - For /s2's acts (`book`, `book_venue`, `send_email`, `send_whatsapp`) to run through AgAPI, either:
     - S2 sends AgAPI's approval link to the guest's phone (a UX change: they tap it), or
     - AgAPI accepts S2's in-chat yes as an attested approval from the sasha product key. That is an AgAPI/EU decision for 1.3.
   - Until then, every act stays on Sasha's own engine in every mode.
2. **Venue cards.** AgAPI's `venues.find_venues` doesn't return the card's fields yet (photo, phone, website, ranking facts).
   That's an additive AgAPI change before `search_venues` can be served from it.
