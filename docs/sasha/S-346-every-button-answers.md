# Sasha 346 · every /group button answers

FINISH LIST line 4 (the SME demo).

## What went wrong

On 5 Nov at about 18:20 Madrid time, Tyler was on /group. He reported two things: "Swap" didn't take, and "Book all planned" did nothing.

Sasha's logs for 17:17–17:30 UTC show the page reading the list every 6 seconds. They show no POST at all: no /group/act, no /upload, no /invite. His presses never left the browser. A probe of every button as the test organiser found five silent paths:

| Button | What the page did | What it said |
|---|---|---|
| Swap, with nothing filled in | greyed out, sent nothing | nothing |
| Swap, with only "who leaves" filled in | greyed out, sent nothing | nothing |
| Swap, with a newcomer but no city | asked the server | "X has no booking to swap." It never named the missing city, and a list with nothing booked could never swap. |
| The invoice, with nothing booked | opened a pop-up after a wait (browsers block that) | nothing |
| Add these, with nothing pasted | greyed out, sent nothing | nothing |
| Any button while another action was still running | greyed out | nothing |

A grey button says nothing, and so does a blocked pop-up. The page already had a rule that outcome surfaces may not go silent (`check-outcome-surfaces.mjs`, S1: a raw `disabled=`). But /group was never put on that rule's list, so the rule never checked it.

## ROOT TEST (written first)

1. **One source.** Every outcome is decided from the group's stored record: the master list as it is now (`groups.view`, which covers the trips, AgAPI's booking record and the vault marks). It is read on each press and never copied.

2. **One place decides.** That place is `booking_signer/group_outcome.py`, through `run(account, action, args)`, which returns `{done, say, missing?, taps?}`. The actions are book, swap, cancel, invite, the invoice and add these. Callers:
   - every /group route: `/act`, `/invite`, `/invoice`, `/upload`;
   - the chat's tools for the same actions: `group_book`, `group_swap`, `group_cancel`, `group_invite_vault`, `group_invoice`, `group_upload`.

   A message written for one button would be a **PATCH**.

3. **Never silent.** `answered()` is the one exit, and `say` is never empty. The outcome says either what was done, or exactly why not and what is missing. What is missing is named in the field's own words from the page: "who leaves", "who comes", "their home city".
   - Book all with nobody bookable → "0 can be booked: 5 are waiting for their passport." plus an **[Invite]** tap.
   - Swap with a missing field → names the field.
   - A valid swap with nothing booked → the swap happens on the list. Who leaves comes off; who comes goes on with the leaver's dates and grade, is planned now, and their new row is said.
   - A valid swap of a booking → AgAPI's swap card, unchanged.
   - Invite → who was invited and how. Everyone already has a passport → "Nobody to invite".
   - The invoice with nothing booked → "Nothing is booked yet…". Otherwise its number and total are said, and its link is shown to tap (no pop-up).
   - Add these with nothing pasted → names what to paste.

4. **The page cannot hold a press back.** No button on /group is ever greyed out. A press while something else is running is told so ("Book all is still running — its answer comes here first"). Every answer, a lost request included, goes through the page's one reader, `heard()`.

5. **The whole class is closed.** Every page that acts (calls `bookingReq`) is now an outcome surface automatically: the prebuild finds such pages itself, and /group and /vault are also listed by name. The five pages that act but are not clean yet are each named in `NOT_YET_CLEAN` (**PATCH**, said). Two checks keep that list honest:
   - a page on the list that is clean fails the build until it is taken off;
   - a page that acts and is on neither list is checked like any other.

Tests: `tests/test_s346_every_button_answers.py`.
