# Sasha 303 — limit HeyGen spend: ONE gate opens and closes every avatar session

## Root test (written before code)

1. **The ONE truth:** `backend/app/avatar_gate.py`. It is the only code that decides a session may open, holds each open session
   (its LiveAvatar session token, server-side only), and closes it (`POST /v1/sessions/stop`, authorised by that token). Minting a
   session token needs the LiveAvatar key, which lives on Vercel only. So the single minting function, `frontend/lib/avatar-mint.ts`,
   is called from one route (`/api/s2-avatar/token`), and only after the gate said yes. Its first act afterwards hands the token
   to the gate. If that hand-over fails, the session is stopped at once, before the browser ever sees the token.
2. **No second copy:** the page keeps no idle timer of its own (the 120 s `FACE_IDLE_S` timers go). Quiet, hidden, closed and
   over-cap are all decided by the gate's reaper on the server. The page only reports events (a beat while open, "hidden",
   "closed"). It never decides a limit. Tests use the same gate (its `MINT`/`STOP` seams), never a separate path.
3. **Whole class:** `frontend/scripts/avatar-gate-303.test.mjs` greps the whole frontend for `sessions/token`. Its one
   home is `lib/avatar-mint.ts`, whose one importer is `app/api/s2-avatar/token/route.ts`, which asks the gate first. The two
   legacy token routes (`/api/heygen/token`, `/api/heygen/token/phuquoc`: /vietnam, /next, the site root) now go through the same
   gate, so an unsigned or guest visitor gets a still. `backend/tests/test_s303.py` pins that a session the gate didn't open
   can't be registered, and that every open one is closed by the reaper.

## Inventory before the change (38e3a08)

Calls to LiveAvatar (api.liveavatar.com), file:line:

| # | where | what | who could call it |
|---|---|---|---|
| 1 | frontend/app/api/s2-avatar/token/route.ts:19 | mint a LITE session token (/s2) | any signed-in account, **guests included** |
| 2 | frontend/app/api/heygen/token/route.ts:15 | mint a FULL session token (/next, /vietnam, site root) | **anyone, no sign-in** |
| 3 | frontend/app/api/heygen/token/phuquoc/route.ts:14 | mint a FULL session token (Phu Quoc demo) | **anyone, no sign-in** |
| 4 | frontend/app/api/heygen/preview/route.ts:25 | read the avatar's still (no session) | anyone (cached a day) |
| 5 | frontend/app/api/heygen/context/route.ts:9,17,43 | read / set the avatar's context (no session) | ops key only |
| 6 | frontend/app/s2/S2Hello.tsx:70,82 | the browser starts a session (`LiveAvatarSession.start`: this is what bills) | the /s2 page |
| 7 | frontend/app/components/SashaAvatar.tsx:170 | the browser starts a FULL session | /next, /vietnam, /vietnam2, site root |
| — | backend/app/api/heygen_chat.py:35 | LiveAvatar calls US (custom LLM), opens nothing | — |

What opened a session (before):
- **/s2 page load.** Every signed-in arrival started a muted live face BEFORE any tap (S2Hello.tsx:252-254, 356). Signed-in
  includes the automatic web guest, so every anonymous visitor to /s2 opened one. It ran until his tap, the hand-off, or 120 s.
- A tap on her face in the corner (S2Hello.tsx:434).
- /next, /vietnam, the site root (app/page.tsx renders /vietnam): FULL sessions for anyone, on that page's start.
- **Tests / harness:** no backend test or CI step calls LiveAvatar. My Playwright walks of /s2 allowed `heygen|liveavatar`
  hosts, so each walk's arrival opened a real session on a TEST guest: **22 walks this session** (s295 to s302 scratch walks),
  each stopped seconds later by the hand-off when the walk typed. WhatsApp never opened one.

What closed it (before): the hand-off after her hello, collapse (Pause, the camera-off line, a session that ended by itself),
120 s of quiet (two client timers), and leaving the page (unmount). Nothing on a hidden tab. A closed tab ran no cleanup:
the session ran on until LiveAvatar's own limit.

**Did "turning my camera off" end the session?** Yes. The camera-off line goes through settle → collapse → letGo, and
`f.stop()` → the SDK's `POST /v1/sessions/stop`. It ends the session, not only the video. But only from the browser: a tab
killed mid-line never sent it.

## The change

- **The gate** (`backend/app/avatar_gate.py`, routes `/api/avatar/{open,opened,beat,close,today}`): open only when ALL hold:
  - a real sign-in (an account whose record carries neither `kanoe_guest` nor `kanoe_test`; never the demo / anonymous account);
  - the reason is `tap` on `s2`;
  - the person's minutes today are under `SASHA_AVATAR_PERSON_MIN_DAY`;
  - Kanoe's minutes today are under `SASHA_AVATAR_KANOE_MIN_DAY`.
  Both caps are Railway settings, and unset means 0 (no avatar). Anyone else is refused, gets her still, and she says so in
  one line when a cap is the reason.
- **The reaper** (every 5 s, on the server) closes a session:
  - on 60 s with nobody talking (`quiet`);
  - when the tab says it's hidden or closed (`hidden` / `closed`);
  - after 30 s without a beat (`lost`);
  - when a cap is reached (`cap_person` / `cap_kanoe`).
  The page closes too, when it can (camera off, leaving): `close`. Talking is heard by the server itself: each of his turns
  (`/api/agent/turn`) and each line of hers fetched for her lips (`/api/s2-voice/pcm`). The page's beat adds his voice on the mic.
- **The log:** one `sasha_measures` row (kind `avatar`) per session, written when it closes, with:
  - who (hashed);
  - why it opened, and when it opened and closed;
  - seconds, and why it closed.
  The founder page shows today's total. SQL 045 lets the table take kind `avatar` and adds the gate's own day ledger
  (`sasha_avatar_day`), the caps' authority. Measures are never an authority (S275).
</content>
</invoke>
