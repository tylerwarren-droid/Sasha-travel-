# CR 54 · Wiring CampusMe into Sasha's agent — the merge note

**Not applied.** This is the exact change to `backend/app/agent/sasha.py` that opens and closes the CampusMe skill and scopes its tools. It is written against `sasha.py` as of `74c14ab` (Sasha 211 Part B), and is to be merged in one step **after Sasha 211 is done**.

Everything else is already on branch `cr/campusme-skill`, and none of it is imported by anything live:
- `agapi/campus.py`
- `agapi/skills.py`
- `booking_signer/basket_visits.py`
- `booking_signer/sql/035_basket_visits.sql`

**Size:** 2 files: `sasha.py` with 9 hunks (about 30 lines added, 4 changed) and one changed line in `tests/test_agapi_guards.py`. There are no new routes and no changes to the frontend contract beyond one optional request field (`tap`).

## Before merging

1. Run `035_basket_visits.sql` in Supabase **after** the deploy that ships the branch. It is tagged in its header.
   - Until it runs, `plan_tour` answers `visits_not_saved` honestly; nothing else breaks.
2. `python -m unittest tests.test_campus_skill_cr54` must pass: 23 tests, 2 of them on Postgres.

## The hunks (`backend/app/agent/sasha.py`)

**1 · Import**, beside `from agapi import v0 as API`:
```python
from agapi import skills as SK   # CR 54 · the open skill (strict spaces in code) and its tools
```

**2 · The renderers.** Add to `RENDER`; `"inline"` means her words carry it:
```python
RENDER.update({"find_schools": "inline", "find_visit_sessions": "inline", "plan_tour": "trip", "save_student": "inline",
               "prepare_registration": "inline", "check_confirmation": "inline", "get_campus": "trip"})
```
`tests/test_agapi_guards.py:207` requires `RENDER`'s keys to equal v0's tools **exactly**, so this hunk breaks it unless the same merge changes that line to
```python
        from agapi import campus as CAMPUS
        self.assertEqual(set(AG.RENDER), (set(API.BY_NAME) | set(CAMPUS.BY_NAME)) - {n for n in API.BY_NAME if n.startswith("_t_")}, "a tool without a renderer")
```
With that change every tool, campus included, still needs a renderer. The `"trip"` kind refreshes the Trip view, where the visits show as journey items.

**3 · `turn()` gains the skill**, via one new keyword argument with a default, so every existing caller is unchanged:
```python
async def turn(account, message, history, session, voice=None, skill=None):
```

**4 · The tool list**, in `turn()`. Replace `tools = tools_for_model()` with:
```python
    tools = SK.tools(skill)          # CR 54 · inside a skill: ONLY its tools; in Sasha: her travel tools
```

**5 · The skill card**, at the end of `system_now()`'s `extra`, before the return:
```python
        if skill == "campus":
            extra += ("\n\nYou're in CampusMe (the person opened it). One step per message, about four lines, one next step. "
                      "Times, spaces and drives only from the tools. Never say a visit is registered unless get_campus says so. "
                      "The school's statement box and Submit are always theirs, on their phone. They leave with “sasha”.")
```

**6 · The dispatch**, in the tool loop. Replace
```python
            t = API.BY_NAME.get(u.name)
            ...
            r = await API.call(ctx, u.name, args)
```
with:
```python
            mod = SK._module(skill)
            t = (mod.BY_NAME if mod else API.BY_NAME).get(u.name)
            ...
            r = await SK.call(ctx, skill, u.name, args)   # a tool outside the open skill is refused, never run
```
The `idempotency_key` line above it stays as it is: it already keys on the `t["idempotent"]` it finds.

**7 · The guard**, in both `guard_check(...)` places at the end of `turn()` (and in `speakable()`). Extend the result while the skill is open:
```python
async def _skill_bad(ctx, skill, text, results):          # new helper, beside _anything_booked
    if skill != "campus":
        return []
    from agapi import campus as CAMPUS
    g = await CAMPUS.call(ctx, "get_campus", {})
    return CAMPUS.guard_check(text, results, (g.get("result") or {}).get("visits") or [])
```
- At each `bad = guard_check(...)`: `bad += await _skill_bad(ctx, skill, text_checked, tool_results)`.
- `tool_results` is a list kept in the loop: `tool_results.append(r)` after each call.
- `guard_strip` already replaces a "claim" sentence. Add one line so a "figure" one becomes "The tour card shows the times.", the same pattern as its price line.

**8 · The route** (`agent_turn`): resolve the skill before the turn, and answer the word itself in one line.
```python
    tap = str(body.get("tap") or "")[:40] or None                 # a skill button's payload ("skill:campus" / "skill:sasha")
    sk = await SK.resolve(account, message, tap)
    if sk.consumed and sk.said:                                   # "campus" → "Let's plan your campus tour." (said once)
        async def opened():
            yield f"data: {json.dumps({'type': 'done', 'text': sk.said, 'skill': sk.skill, 'guard': [], 'ms': {}})}\n\n"
        return StreamingResponse(opened(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
```
Then pass `skill=sk.skill` through `turn_with_quiver(...)` into `turn(...)`, which is one argument on each of the two calls. The early `if not message: … 400` must allow a tap with no text: `if not message and not tap`.

**9 · The space shown.** Add `"skill": skill` to the final `done` event so the UI can show the space label ("You're in CampusMe — say “sasha” for travel"), as the WhatsApp and web chats already do.

## What this does NOT change

- **The basket.** `basket.py` is untouched. Visit rows (kind `visit`) carry no price, so `basket.total()` is unchanged. Reads that use `basket.items(..., LIVE)` on a tour's trip will also see its `suggested` visits; they are on the tour's own trip, never a travel trip. If that matters on the Trip panel, filter `kind != 'visit'` in the panel. That is one line, and Sasha 211's call.
- **WhatsApp and the current web chat** keep today's CampusMe flows (CR 53 decision 3), untouched.
- **No new outbound requests.** Schools are read only by the same paced, robots-first reader, and the cloud browser opens only under `HO.dpa_ok`.

## Afterwards (not in this merge)

The agent suite gets a CampusMe conversation: "campus" → plan a tour → details → prepare (a guest without the DPA gets the school's page) → "sasha". It is added to `scripts/agent_suite.py` once the hunks are in.
