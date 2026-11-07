# Sasha 358 — ONE group engine (the roster + a trip's selection) that every door uses; /group is its first full view

**Found (Tyler's dry run, 7 Nov 09:43–10:05, /group, Jean Incorporated):**
- A new trip could only be started in the chat.
- "Add these" put all 20 straight ON the open trip.
- "✓ on it" was a label, so nobody could be taken off.
- Edit → Save didn't answer.
- There were six "London 2026-11-17" trips, three of them empty.

## The engine — `backend/booking_signer/groups.py`

The engine holds the roster (`group_people`, now with **role / department** beside grade: `sql/059`, applied 7 Nov) and each trip's selection (the links, 351). They change **only** through two functions:

- **`create_trip(destination, dates, area, who)`** is the one way a trip is made.
  - It resolves who's going **first**. If nobody is ticked, only unknown names are given, or the chat gives no `who`, **nothing is made** and that is said ("who's going?").
  - The same company, place and dates as an existing trip reopens that trip (345).
  - Each person is put on through `set_on_trip` and planned from their own home airport.
- **`set_on_trip(person, trip, on|off)`**:
  - **on** links the person and plans them.
  - **off** works only when nothing is booked for them; it is said, and their plan is dropped.
  - **booked**: they stay on, and **Cancel is offered** (352).
  - **the last one off** ends the trip, and that is said.

**Nothing is ever deleted because a page was read.**

**`state()`** is the one view: the roster with each person's switch (the record itself), the open trip and its list, and the trips.

**Every door calls the engine:**
- /group: `POST /group/create` (Go), `/group/switch`, `/group/people` with `on_trip`, and `/group/upload` (in a new trip this fills the roster only, ticked).
- The chat: `group_start`, `group_choose`, `group_upload`.
- The swap's list path.

## The view — `frontend/app/components/group/GroupView.tsx`

This is one component, and /group renders only it. S2's and /next's group tab come next (359).
- **New trip:** roster → where, dates, hotel area → tick (or upload, or add someone) → **Go**.
- **Manage:** who's on it **first** (a real switch, status, price, passport), then the roster's others (a switch puts them on) and someone new (onto the roster **and** the trip, said).
- **Every press answers in words**, including Save with nothing changed, New trip and Edit.

## No build depends on the network

Every Vercel build had failed since ~08:40, because `next/font/google` couldn't reach Google Fonts from the builder; the same code had built Ready at 07:16.

The font files now live **in the repo**: `frontend/app/fonts`, holding Geist, Geist Mono, DM Sans and DM Serif Display from google/fonts, each with its OFL licence beside it. They are served by **one module** (`fonts.ts`, `next/font/local`). The build compiles with the network blocked.

## The existing empty trips

There was one cleanup, by exact id, approved by Tyler: Jean Incorporated's three empty London trips (17–21 Nov). The ids were `e9f9d122-…`, `437d0837-…` and `54cfa990-…`. They were deleted under a guard that refuses any trip with someone on it; 0 are left. No other organiser had an empty trip.

## Tests

- **`tests/test_s358_group_engine.py`:**
  - the whole walk;
  - off a booked trip offers Cancel;
  - **no door can make a trip with nobody on it, and no read deletes one**;
  - Go needs who and where;
  - a new-trip upload never puts anyone on a trip;
  - Save always answers;
  - the chat's start makes no empty trip;
  - one source (a scan of the store's writers);
  - the page is the component, and every press says something;
  - 059 and the store's writes on real Postgres.
- **`tests/test_s358_fonts.py`** fails on any `next/font/google`, on `next/font/local` outside the module, on a missing or non-font file, on a family without its licence, and on any build-time remote asset.
- **Suite:** 3391 tests; the only failures are the 2 baseline ones.

## Proven on /group alone (7 Nov, project.kanoe.ai, the test organiser, Lusa Obras Demo (fictional), no chat)

| Step | What the page said |
|---|---|
| New trip → roster | 25 people to tick |
| Lisbon 24–27 Nov, tick 12 → **Go** | "The Lisbon trip (2026-11-24 – 2026-11-27): 12 people on it. Planning each from their own home airport now…" (2.5 s) |
| Planned | each from their own airport (BIO, BCN, SVQ, VLC, MAD …): 7 planned · 5 needs vault |
| Manage | "On this trip (12)" first, then "Add from your roster (13 not on this trip)" |
| Remove one (nothing booked) | "Nuria Prieto is off the Lisbon trip — their plan is dropped; nothing was booked for them." |
| Add from the roster | "Javier Moreno is on the Lisbon trip — planning them from VLC now." |
| Someone new | "Added Rui Novo (fictional) to the roster and the Lisbon trip — planning from their home airport now." |
| Edit → Save | "Saved — Laura Lozano: role technician. Every trip reads it from here." · unchanged: "Nothing changed — Laura Lozano's details are as they were." |
| Edit · New trip | "Editing Laura Lozano — change what's needed, then Save." · "A new trip: where and when, then tick who's going… Nothing is made until Go." |

**Found by the proof:**
- **New trip and Edit said nothing** (they left "Edit…"). Fixed at the source, and a test now holds that every press says something.
- **Go's first press, while the backend was redeploying**, said "Sasha's server didn't answer — nothing was changed", which was true (nothing was made). The next press answered in 2.5 s.
- **Two later "didn't answer" lines** were this machine's own network dropping (`ERR_NAME_NOT_RESOLVED`), not Sasha. Each press was repeated and answered.

Book all → invoice was not part of this proof; 351 proved it on the same organiser.
