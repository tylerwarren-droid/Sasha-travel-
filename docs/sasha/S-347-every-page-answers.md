# Sasha 347 · every page that acts answers — the NOT_YET_CLEAN debt cleared

FINISH LIST line 4 (the SME demo). This ticket follows the NO PATCHES rule (CLAUDE.md, 6 Nov).

## Cause

Sasha 346 found that /group's buttons said nothing when pressed. To make that impossible for /group, it made the prebuild check every page that acts, meaning every page that calls `bookingReq`. Five pages failed that check, and 346 parked them on a list called `NOT_YET_CLEAN` instead of fixing them. That list was a hand-kept exception, which is a patch.

Clearing the list exposed a deeper cause: **the check itself could not see the whole class.** It had four holes:

1. **Its comment-stripper was a regex.** The regex read the `/*` inside `accept="image/*"` as the start of a comment and erased the real code that followed, up to the next `*/`. As a result, S2's 📎 button (`disabled={busy || working}`) was never checked at all.
2. **Its `.then` rule read a fixed 600-character window of text.** A short chain that did end in `.catch` could still be reported, and a long chain that ended in `.catch` was reported because the window cut it off.
3. **It could not see a floating promise.** A call such as `prepare()` or `onClick={() => send(t)}` starts an async action that nothing watches. If it failed, nobody would hear about it. There were 54 of these across the acting pages.
4. **It could not see an async function handed to a slot that expects nothing back.** For example, `send={send}` passed into a prop typed `send: (t) => void`. Every call made through that prop floats, and the line that creates the problem is not the line where the call happens.

## One source

There is **one outcome path on the page**: `frontend/lib/outcome.ts`. It is 346's `heard()`, moved so every page shares the same copy.

| Function | What it does |
|---|---|
| `heard(name, res)` | The server's own words (`say` / `why` / `message`). If there are none, it says what happened to the request. Never empty. |
| `failed(name, error)` | A request or step that threw → the words to show. |
| `needs(name, fields)` | An action pressed without what it needs → "Send needs a message — type one, or tap the mic to talk." |
| `stillGoing(running, pressed)` | A press while something else is running → it is told so, never ignored. |
| `again(title)` | A card's choice pressed a second time → "Already answered — …. Nothing more was sent." |
| `observe(promise, name, tell)` | Every promise a page starts. If it fails, that failure is told: to the person, or to the console (named) for a step that isn't theirs, such as a timing note. |

The server side is unchanged. Each route says what was done, or exactly why not; for /group, that is `group_outcome.py` from 346.

## Fix (the whole class)

**The check reads code the way the compiler does.** `scripts/check-outcome-surfaces.mjs` now uses TypeScript's own parser and type checker:

- **Comments** are found by the parser. Each is blanked to spaces, so a finding's line number is the file's real line number.
- **S1** catches any JSX `disabled` attribute, whether or not it has a value.
- **S2** catches:
  - `void <call>`;
  - a `.then` chain with no `.catch` (and not awaited or passed into `observe`);
  - a floating promise statement or arrow body;
  - a promise-returning function given where a `void` callback is expected.
- **Fixtures.** Every hole above is a fixture that the checker must catch before it vouches for any page. The type pass has its own fixtures too.
- **No exceptions.** Every page that calls `bookingReq` is checked. `NOT_YET_CLEAN` is deleted.

**Every acting page goes through `lib/outcome`.** This covers 17 files and 82 sites.

- **S2:** nothing is greyed out.
  - Send with an empty box says what it needs.
  - New chat, while something is running, says so.
  - 📎, while an upload or Sasha's reply is running, says so.
  - A card's second tap says it was already answered and sends nothing.
  - Copy says "Copied ✓", or why it didn't work.
  - Every send (typed, spoken, a chip, a card choice, a queued message) goes through `sendNow`, so a failure is told in the conversation.
  - The "Did it go through?" tap now answers even when noting the answer fails.
- **Booking cards** (ChatBookingDo, the flight / hotel / trip tests): Continue names the missing fields. Every prepare and yes is observed, and a failure shows on the card itself.
- **Founder pages** (Demo controls, Founder words, Gmail, Outlook, Invite, My bookings): every press is observed, and a failure shows in that page's own line.
- **Background reads** (polls of the trip and the master list): each is observed, and a failure is logged to the console with its name.

## What this does NOT cover (debts, each needing its own root ticket)

- **Pages that act through a direct `fetch(`** instead of `bookingReq` are not "acting pages" by this check's definition. There are about 20 such files with about 100 silences: S2Hello, VoiceButton, /next, SashaChat (the CTO's file), /vietnam, and others. The root fix is ONE client for every request a page makes, so the check's definition becomes exact.
- **A `.catch` that tells nobody** (for example `.catch(() => {})`) counts as "observed" here. It silences the symptom. The root fix is a checker rule: a catch on an outcome surface must tell someone, through `observe`.

Tests: `backend/tests/test_s347_every_page_answers.py`. The prebuild itself is the main test.
