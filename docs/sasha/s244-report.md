# Sasha 244 — report (11 Oct 2026) · AgAPI routed to LIVE per operation, the demo airline kept, a link for EU

## Live
- **Sasha main:**
  - **974b0b7**: Railway **6afe895b**, **DEPLOY GATE: PASS** ($1.29 / 241 calls). Vercel sasha-travel-hdyp **9EjvmDijBfVGVyLkWC4NCD9Q6u5i**: success.
  - **`SASHA_AGAPI_ROUTE`** was set with no redeploy of its own, so 974b0b7's deploy was the one restart (no other deploy was running). READY was confirmed after.
- **Checks:**
  - Units **2053 OK** (11 new in `tests/test_s244.py`).
  - Frontend `npm test`: 37 pass (3 new, `gmail-offer`), 1 fail. The failure is the same AgAPI-hub one as before.
  - tsc clean; `next build` OK; lint 0 → 0 on MailboxConnect.
- **S1:** parity on and parity off are both byte for byte 243's (no tool or prompt change).

## 0 · EU234 link: DONE (row 747)
- A fresh one-click link for tylerwarren+eu234@gmail.com was posted as "EU234 LINK …" in **row 747**, right after it was generated and before anything else.
- **Supabase's link lifetime was not raised.** It is a project-wide auth security setting, so it is Tyler's to change in the dashboard (Auth → Email OTP expiry) if he wants it.

## 1 · AgAPI routing: DONE (routing); two live proofs wait on CR's agapi-live deploy
- **The routing table** (production, `SASHA_AGAPI_ROUTE=activities=live,entry=live,cards=live,subscriptions=live,money=live`):

  | op | goes to |
  |---|---|
  | activities.suggest / activities.verify | **live** |
  | entry.check / entry.prepare | **live** |
  | cards.* (mine, intake, ask, which, rental_cover, accident_*, moment, claim_*), and keep.put for a card | **live** |
  | subscriptions.find / cancel_plan / cancel | **live** (real Gmail, connected by the person; live has no fake inbox) |
  | money.flight_check / flight_claim / bag_check / bag_claim / claim_status, for a **real** airline | **live** |
  | money.* for **test inventory** | **sandbox** (Example Air, test mode) |
  | users.register, approvals.*, sandbox.simulate_approval | follow the call they belong to |

- **What counts as test inventory:**
  - Example Air (EX) or Duffel Airways (ZZ);
  - **or a flight in the person's own Sasha basket**, matched by booking reference, or by carrier + number (+ day).
- **Why the basket rule matters:**
  - Sasha's flights are all Duffel TEST inventory (258 of 258 basket flights have `is_test`), yet they carry **real airline codes** ("UX 1153 · Air Europa").
  - Without this rule, a claim about one of Tyler's made-up flights would be emailed to the real airline from live.
  - If the basket can't be read, the claim goes to the sandbox, never to live.
  - A claim's filing and status stay on the AgAPI where its case was opened.
- **Each AgAPI has its own end users.** "all=sandbox" in the variable sends everything back to the sandbox in one line. With nothing set, the old switches apply (the sandbox), so behaviour is unchanged.
- **Proof** (production, scratch C, specimen ES passport):
  - **Activities from LIVE: works, but Lisbon has no list on live yet.**
    - Madrid, Sat 24 Oct → the activity cards: Prado 10:00–20:00 €15 (free 18:00–20:00), Reina Sofía, Thyssen, Palacio Real, no Real Madrid home match.
    - Lisbon → "no list of official sites": agapi-live answers "I don't have a list of official sites for Lisbon yet" (0 candidates; the sandbox has 7, from CR 85's reads).
  - **Entry from LIVE: routed, but the answer needs CR's deploy.** agapi-live (ae81483b, 17:31) has entry.check **without** `passport_country`, so Sasha falls back and asks for the passport, as designed.
  - **These two need cr/85 (with 8dd1509) on agapi-live.** That's CR's release, so I asked CR to deploy it and have not touched agapi-live. Its own deploys at 17:48–18:26 had replaced my sandbox change once in 243.
  - **A delayed TEST flight → money back via Example Air (sandbox) → filed:**
    - "EX123 MAD→LIS on 10 Oct, 4 h late, ref EXTEST, Alex Scratch" → "you may be owed €250".
    - "Yes, please file the claim" → read-back: email to claims@example-air.example, €250 under EU 261/2004, by bank transfer.
    - "Yes, go ahead and send it" → filed.
    - Status → "filed with Example Air on 11 October 2026 (ref sbx_claim_19z77k3k) … reply due by 10 November 2026".
- **Seen, not fixed (out of scope; worth a ticket):** in the activities turns she "corrected herself" twice. She said she had given Madrid's hours "without actually running the check", though the card had rendered. It looks like the turn's claim guard doesn't see fine-print results.

## 2 · Jon and Gmail: DONE
- `SASHA_GMAIL_ACCOUNTS` was left as it is.
- /you now shows the full Gmail connect form only when:
  - the sign-in address is a Gmail one (gmail.com / googlemail.com);
  - a Gmail is already connected or expired;
  - or they press **"I have a Gmail account"**.
- Otherwise it shows one line: "You signed in with an iCloud address. Connect Gmail only if you have a Gmail account — Sasha doesn't read Outlook or iCloud mail yet." Only the domain is named, never the address.
- Proved by `scripts/gmail-offer.test.mjs` (Jon's iCloud → the quiet line; Gmail, connected, expired or "I have one" → the form). It was not walked on Jon's account, which is never used.

## Cleanup
- Scratch C (f1dd8d08) was purged and deleted (200). **0 rows left** across 115 account/user/id columns.
- No turn on Tyler's or Jon's accounts. No booking platform requested from this machine. No live Places.
