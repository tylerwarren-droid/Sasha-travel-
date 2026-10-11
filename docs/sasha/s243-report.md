# Sasha 243 — report (11 Oct 2026) · Gmail subscriptions live for Tyler + Jon, entry check from the Keep

## Live
- **Sasha main:**
  - **2913e9a** merges CR 84 and adds items 2–4. Railway **04e6b2cd**, **DEPLOY GATE: PASS** ($1.28). Vercel sasha-travel-hdyp **25U8p5WuANzjAr9ywLLAgcuX6wtb**: success.
  - **9028243** puts the cancel page in the chat as a card (found by the proof). Railway **60183370**, **PASS** ($1.28). Vercel **FpUSQCFbqiHV1x2XiN7skcfMRcpP**: success.
  - **1323f00** keeps still-paid subscriptions in the list and names the list's real source (both found by the proof). Railway **646f5f7c**, **PASS** ($1.28). Vercel **9Z2tWkZ76ACnVH1MCtmHH2ydyMyk**: success.
  - Every push went to main only, with no Railway deploy running at the time. READY was read from GitHub commit statuses, since the Vercel connector answers 403.
- **AgAPI (separate repo):**
  - The change is one commit, `passport_country` on entry.check. It is **1accac6** on cr/84 (branch `sasha/243-passport-country`) and **8dd1509** on cr/85 (branch `sasha/243-on-cr85`).
  - The sandbox runs **0448f98d**, built from cr/85 @ e3c5e84 plus 8dd1509.
  - The CR tab's cr/85 deploys at 17:48, 18:07 and 18:26 had replaced the first deploy (ac615ac6). The CR tab has now fast-forwarded its local cr/85 to 8dd1509, so its future deploys include the change.
  - CR's push of cr/85 to GitHub is waiting on Tyler's approval (CR's mailbox row 745). I did not push it for them.
  - Production Sasha uses the AgAPI **sandbox** (`SASHA_FINE_PRINT_VIA` and `SASHA_SUBSCRIPTIONS_VIA` are unset).
- **Checks:**
  - Units **2042 OK** (9 new in `tests/test_s243.py`, plus CR 84's 5). AgAPI: **418 OK**; contract and vendored checks ALL PASS.
  - Frontend `npm test`: 34 pass, 1 fail. The failure is the same AgAPI-hub one 241 and 242 reported.
  - tsc clean. `next build` OK; one retry was needed, after a Google-font lookup error that has nothing to do with this change. Lint: 0 → 0 on the changed files.
- **S1 fingerprint:**
  - Parity on: system `9a02cfe47274…` is unchanged, with **53 tools**. The tools hash is now `8a6aeb0b306b…` (was `aeb49593d4d0…`), from CR 84's new find/cancel tool descriptions. Nothing was removed.
  - **`SASHA_S1_PARITY=off` is byte for byte 242's off file** (24 tools).

## 1 · Merge cr/84-s2: DONE
- **Merged at 90deb60.** The one conflict was in S2App, where 241 had moved the cards to `components/cards/`. The SubscriptionsCard now lives there too.
- **Proof** (production, scratch B, fake inbox, test mode):
  - "What subscriptions am I paying for?" → the consent sentence, word for word.
  - "Yes, go ahead." (a later turn) → the card: FitBox €34.90 (renews 31 Oct, expected), Netflix, Spotify €10.99 (10 Nov, expected), Amazon Prime (yearly), iCloud+, ChatGPT Plus ("doesn't say how often"). About €67.03 a month. No email body is kept.
  - "Cancel Spotify" → read back: "Spotify's own cancel page … you press cancel".
  - "Yes" → a **handover card** with spotify.com/account/subscription; she says it isn't cancelled until they press cancel and Spotify confirms.
- **Found and fixed by the proof:**
  - **(a) 9028243:** she said "the cancel page is in the chat now" and nothing was there.
  - **(b) 1323f00:** on a second run, Spotify (its page already handed over) dropped out of the list, but the €67.03 total still counted it. It now stays listed, marked "cancel page handed over — not cancelled yet".
  - **(c) 1323f00:** a later list on /next said "From statement" for a receipts list. The source is now remembered per account.

## 2 · Jon on Gmail: DONE
- **Account check:** 4ff7c9c1 is `jonc…@icloud.com`. It was created 8 Oct and is named as Jon in 232's and 237's reports. I only read it; no turn and no message.
- **Allow-list:** `SASHA_GMAIL_ACCOUNTS=4ff7c9c1-4215-46fd-a69f-c181d093db97` was set with no redeploy of its own. 2913e9a's deploy was the one restart, at a quiet moment, and READY was confirmed after.
- **What's left for Jon and Tyler:**
  - They connect Gmail themselves on /you. Nothing of theirs was connected.
  - Google's testing mode admits only listed test users, so **Jon's Gmail address must be on the OAuth app's test-user list in Google Cloud** (Tyler's console). I can't do that from here.

## 3 · Entry check from the Keep: DONE
- **How it works:**
  - Sasha sends the passport's issuing **country**, read from its mask ("Passport ES ••••042"; the country is the mask's public part). Nothing is opened and no number is sent; the body is `{end_user, destinations, passport_country}`.
  - AgAPI uses that country only when its own Keep has no passport.
  - An AgAPI without the new input answers `invalid_input`, and Sasha asks again as before. That fallback is how the CR redeploys showed up: the answer quietly went back to "I need your passport's country".
- **Proof** (B, production, with the specimen ES passport saved):
  - "Do I need anything to enter the UK? I land in London on 2 November."
  - On **/s2 and /next** → "You need an electronic travel authorisation (ETA) … GBP 20 … Apply by 28 October 2026 … Your Spanish passport is in your Keep." She didn't ask for a nationality.

## 4 · All three surfaces: DONE
- **/s2:** the card (proof above).
- **/next:** the same SubscriptionsCard through SHARED_KINDS. Proof: "What subscriptions am I paying for?" on /next → the card with the same six, source "receipts (a fake inbox — test mode)".
- **WhatsApp:** rehearsed in process on 9028243's code. The scratch guest was linked to a FICTIONAL number (+44 7700 900243, Ofcom's drama range), every send was captured, and nothing went to a phone.
  - consent → "yes" → her words plus "*Your subscriptions*", one line each (service · price · renews), "About EUR 67.03 a month", and "See the card: https://project.kanoe.ai/s2".
  - "Cancel Spotify" → read-back → "Yes" → "Tap to finish: https://www.spotify.com/account/subscription/".

## Cleanup
- **Deleted (200 each):** scratch A (6d52d84f), B (7912d677) and the WhatsApp guest (6c173150).
- **0 rows left** across 115 account/user/id columns in public and auth.
- **Not touched:**
  - Tyler's and Jon's accounts and Gmail;
  - any booking platform;
  - live Places (none was called).
