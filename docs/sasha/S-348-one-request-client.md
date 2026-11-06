# Sasha 348 · ONE client for every request a page makes

FINISH LIST line 4 (the SME demo on S2). This ticket clears Sasha 347's two debts, under the NO PATCHES rule.

## Cause

Sasha 347's check only knew a page as acting when it called `bookingReq`. Every other way a page reaches the network went unseen: 141 direct requests across 81 files (`fetch(` ×133, EventSource ×2, WebSocket ×2, sendBeacon ×2, axios ×2).

A `.catch(() => {})` was counted as "observed" even though it tells nobody. That left 150 empty catches.

There were two consequences:
- Pages such as S2Hello and VoiceButton were never checked at all.
- Within checked pages, a failure could be swallowed whole.

## One source

**`frontend/lib/request.ts` is the one place a request leaves the frontend.** It is built on `lib/outcome`, and every failure is told by name before the caller sees it. It offers one replacement for each direct way a page used to reach the network:

| Use this | Instead of | What it does |
|---|---|---|
| `reach` | `fetch` | Same signature; tells a failure before rethrowing it |
| `request` | — | JSON in and out; never throws, gives the failure back as words |
| `events` | `new EventSource` | Same signature; tells its drops |
| `socket` | `new WebSocket` | Same signature; tells its errors |
| `beacon` | `sendBeacon` | Same signature; falls back to a keepalive `reach` |
| `axios.post` | axios | The CTO's one use, built on `request`. The axios package is gone from package.json. |

**`lib/outcome` gains three things:**
- **`noted(name)`:** a catch's teller for a step that isn't the person's own; it names the failure in the console.
- **`announce(text)`:** the page's one line to a person, for pages without a message area of their own.
- **`failed()`:** now says a lost connection plainly: "… couldn't reach Sasha — your connection seems to be off."

## The whole class: the prebuild refuses

These are refused with **zero exceptions and no list**:

- **R1 — any direct request** anywhere in the frontend outside `lib/request.ts`: `fetch(`, `window.fetch(` and the like, EventSource, WebSocket, sendBeacon, XMLHttpRequest, or an axios import.
- **S4 — any catch that tells nobody:** `catch {}`, `catch { /* … */ }`, `.catch(() => {})`, `.then(ok, () => {})`.
- **S5 — a press whose failure is told only to the console:** inside a JSX event handler, `observe(…, toConsole)` or `noted(…)`. The person pressed, so the failure is theirs to hear.

**What counts as acting** is now found, not listed: every file in `app/` and `lib/` that imports the request client (or the booking client built on it). The server's own route handlers in `app/api/` are excluded, because they answer a page and the page tells the person. That gives **74 surfaces**.

**The S2 rule's `.then` half** now lives only in the type pass. The type pass can tell a promise that is stored or returned (whoever receives it observes it) from one that is dropped.

**Every rule has fixtures** that the checker must catch before it vouches for any page.

## The move (mechanical, and Stage B's last step)

`node scripts/one-client.mjs --write` rewrites each direct request with the drop-in that has the same signature. It is also Stage B's **last** step after a CTO drop (see CLAUDE.md).

Then, through `lib/outcome`:
- **Empty catches** became `noted('<what it was doing>')`.
- **Promises nobody watched** became `observe(…)`.
- **The 20 greyed-out buttons** now answer instead (`announce` with `stillGoing` / `needs` / `again`).
- **The 56 presses** whose failure went only to the console now `announce` it, in plain words.
- **VoiceButton:** its connection failures go to its own mic line (`reportMicError`).
- **S2Hello:** a face that can't start (other than the gate's refusal) is announced.

Tests: `backend/tests/test_s348_one_request_client.py`. The prebuild itself is the main test.
