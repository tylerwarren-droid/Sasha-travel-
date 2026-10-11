# Sasha 242 — report (11 Oct 2026) · fix what EU's walk found (row 730)

## Live
- main **3ac7db1** (items 1–4): Railway **be471cc5**, **DEPLOY GATE: PASS** ($1.28 / 234 calls). Vercel sasha-travel-hdyp **8W7nTTWPmgx47ykWHAZGq9xGPUqP**: success.
- main **d995829** (the arrival card, found by item 1's proof): Railway **929b0ec8**, **DEPLOY GATE: PASS** ($1.27 / 234 calls). Vercel **B8BzEvbbmtZiFHpAVFAjkDECgWbF**: success.
- Both were pushed to main only. The other Railway project ("resplendent-delight") and the "sasha-travel" Vercel project fail on every code push, 241's included; neither is this service.
  - The Vercel connector answered 403 for this team today, so READY was read from GitHub's commit statuses for the sha.
- Units: **2029 OK** (12 new in `tests/test_s242.py`). Frontend: `npm test` 34 pass, 1 fail. The failure is the same one 241 reported (the AgAPI-hub page's "Buyer (region): no source"), which this change doesn't touch.
- Typecheck clean; `npx next build` OK; lint: no errors added (TripPanel 14 → 14, every other changed file 0 → 0).
- **S1 fingerprint:** system `9a02cfe47274…` (was `69ac37e28125…`; the one-total line, by 241's parity, is S2's capability text). Tools `aeb49593d4d0…` and **53 tools**, both unchanged.
  - **`SASHA_S1_PARITY=off` is byte for byte 241's off file**, i.e. 228's baseline.

## 0 · Cleanup: DONE (row 734)
Only keep_items `37405b9a…` was deleted from the founder account.

## 1 · Passport to the wrong account: FIXED
- **Cause:** EU's specimen landed in the founder's Keep at 14:49:29 CEST. 241 was deploying then, and the old frontend still let the founder cookie win.
  - One stale path remained after 241: `lib/guest-auth.ts` decided "founder" from whether the founder cookie *existed*.
  - It now asks `/api/auth/whoami`, so it follows 241's rule: a real sign-in wins.
- **Proof** (production, through the site's own proxies, as a real-address scratch account A, `tylerwarren+s242a`):
  - whoami → `acting=user`.
  - The Keep page's POST → **201 "Passport ES ••••041"**. The `keep_items` row's account_id is **7536a3f0**, scratch A's own; it isn't the founder's.
- **A second defect, found by that proof:**
  - "I'm flying to Bangkok on 20 November. Please fill my arrival card from my passport" → she named "a Spanish passport ending 041" from A's Keep, but said the card's passport section "wasn't pulled in".
  - Cause: AgAPI's `entry.prepare` reads AgAPI's own Keep. A passport saved on /keep lives in Sasha's.
  - Fix (`d995829`): the card's Keep section takes the person's own mask from Sasha's Keep. The mask only; the number never leaves the Keep. The count she says is corrected to match.
  - **Proof after deploy:** the same words → "Two of its five sections are filled in: your passport details come from your Keep (**Passport ES ••••041**), and your arrival date of 20 November comes from your trip". The official site is given; she never submits.
- **Still open (AgAPI side, not this repo):** `entry_documents` ("what do I need?") can't read the passport's country from Sasha's Keep either. `entry.check` takes only AgAPI's own Keep, so it needs a `passport_country` input over there.

## 2 · Privacy (strangers' trips): FIXED
- **The trips EU saw were the founder's**, shown because the founder cookie won before 241.
  - The server was already scoped to the account acting: `/plan` and `/journeys` use `account_for`.
- **New:** per-person browser storage is cleared on sign-out or a change of the person acting. The rule is in `lib/acting-rule.mjs` (tested) and `SignedInLine`. It covers:
  - `sasha_last_session`, `s2_met`, `s2_hello` and `kanoe_onboarding_draft`;
  - all sessionStorage.
- **Proof: ONE headless Chromium, one context, production** (one-click links, as EU signs in):
  > A signed in → whoami `user` s242a · badge "Signed in as tylerwarren+s242a@…" · plan "3 Days in Lisbon…" (trip 3a6e3619) · A's 4 per-person keys set
  > SAME browser, B signed in → whoami `user` s242b · `sasha.who`=B · **all 4 keys null, sessionStorage 0** · **plan none, plans 0**, journeys only B's product tabs · badge "Signed in as tylerwarren+s242b@…"
- Tyler's own Chrome wasn't used, because a scratch sign-in there would have cleared his per-person keys.

## 3 · One total, one currency: FIXED
- **Before:** the chat said "€496 ALL IN" (the basket); the Trip tab showed the planner's dollar estimate ("Hotels $340").
- **Now:**
  - `/plan` carries `trip_total`: the basket's own euro figure (the same rows and sum `get_total` says), read as they stand, with no re-search or re-price on the 6-second poll.
  - The Trip tab shows "All in €…" with ✈️ Flights / 🏨 Stays (estimate). It falls back to the old estimate only while the basket has no euro price.
- **Persona (S2, and S1 via parity):** one total in euros, the figure the Trip tab shows, and never "an earlier draft, an earlier quote or a previous version".
- **Proof (A, production):** "What does the whole trip come to?" → she says "the whole trip comes to about **€445** for you, everything included". The Trip tab's `/plan` returns `trip_total` **€445.08** (flights €132.28 quoted + stays €312.80 estimate). The same figure in the same currency.
  - She didn't repeat the earlier figure (€360 before the outbound flight was added), but she did say "Now that a Saturday flight is in". That explains the change; it doesn't quote a draft.

## 4 · Small: DONE
- **Rehearsal card:** already founder-only (`GW.rehearsal`; 175). EU saw it as the founder, before 241. Now pinned by a test that a real account never gets it.
- **Keep number fields:**
  - They are `type=text`, `autocomplete=off`, with password managers told to stay out (`data-lpignore`, `data-1p-ignore`).
  - They are still masked on screen (CSS), and each has its own `name`.
- **Spa / Hammam Al Ándalus:**
  - Google found it: its Madrid listing is "Hammam Madrid Plaza Mayor", read at 12:34 UTC as `madrid.hammamalandalus.com`.
  - The founder's online-only filter (187) dropped it, because its own site carries a CAPTCHA.
  - A venue whose own site has a CAPTCHA now counts as bookable online, by the guest's own hand: "their own site (you finish it — it has a CAPTCHA)" (the 175 flow).
  - Real accounts never had that filter.
  - **Proof (scratch B, production):** "Find me a spa in Madrid for this Saturday afternoon, ideally Arab baths. Don't contact anyone." → 5 cards, among them **"Hammam Al Ándalus Plaza Mayor is the classic Arab baths experience, with over six thousand reviews"**; nobody was contacted.

## 5 · eu234 link
A fresh one-click link for tylerwarren+eu234@gmail.com was generated and not opened (unspent). It is posted as **"EU234 LINK …" — mailbox row 735**. It isn't in this repo.

## Cleanup
- Scratch A (7536a3f0, `tylerwarren+s242a`: a passport, a Lisbon plan) and B (8fa3b5e9) were purged and deleted (200 each). **0 rows** remain in every public and auth table with an account/user column.
- Their one-click links were spent in the headless browser. Nothing of Tyler's or Jon's was touched, and no booking platform was requested from this machine.
