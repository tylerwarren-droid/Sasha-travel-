# Sasha 232 · report

Main **70e83ba**. Commits: 5ecace9 (real on /s2 + gate key/cost) → 26c60dd (direct first, the founder's stand-in on /next only) → 172a866 (iPhone voice/face, the service in the draft, the Sonnet 5.5 price) → 70e83ba (a late face shown with the tap).

**Checks**
- Gate (Railway 42371b81): **PASS 202 / FAIL 0**; demo safety 307 of 310 (3 known gaps).
- Units: 1865 OK.
- Vercel: production Ready.
- S1 fingerprint: **byte-identical to 228's baseline** (system 4e2560d4bdfd…, tools 5334edda76ee…, 24 tools). Nothing in 232 touches S1's prompt or tools. The founder's stand-in still applies on /next exactly as before.

## 1 · Real bookings for Tyler and Jon
- `ladder_routes._s2_demo_account`: the hard-coded `founder(account) or` is dropped. Only `SASHA_S2_DEMO_ACCOUNTS` decides, and it is now **empty**. It was set after 5ecace9 was READY and took effect with deploy 26c60dd.
- **Also changed:** `SASHA_DEMO_STANDIN=1` made the founder's non-restaurant bookings (tattoo, dog walker) stand-ins on /s2 too. That stand-in is now /next only: every /s2 read carries `s2_demo`. On /next it is unchanged.
- `SASHA_CALLS_ACCOUNTS` = Jon (4ff7c9c1…). It was unset, so nothing was removed. The founder's calls are unchanged (always on).
- Flights stay on Duffel TEST and payments on Stripe TEST (untouched).
- **Proof:** scratch guest 577c2014, not in demo mode, said "Book me a table for 2 at a tapas place near Gran Vía tonight at 9". She picked Tapa Tapa Montera, answered "Email them, please.", and reached `hold_venue(awaiting_yes)`. Her reply named the real restaurant: "The email is drafted… asks Tapa Tapa Montera for a table for 2 tonight, Saturday 10 October, at 9… Shall I send it?" The stream never contained "TEST stand-in". It was **not** sent, and no venue emails went out (0 in 2 h). Transcript: `s232-shots/proof-real-venue-tapas.txt`.

## 2 · Voice and face on iPhone: root cause and fix
- **Voice.** iOS Safari plays sound only from an element that a tap has already played.
  - Every reply was a **new** `Audio()`, played after the TTS fetch and outside any tap. iOS refused it (NotAllowedError), and the refusal was swallowed. She was silent while the toggle said "🔊 Voice on".
  - 230's `unlock()` played an empty `new Audio()`. That unlocks only that empty element. 230's recordings ran Chrome with `--autoplay-policy=no-user-gesture-required`, which hid this.
  - **Fix:**
    - She now speaks through **one** element, primed with a silent clip synchronously inside the tap and then reused.
    - `navigator.audioSession.type = 'playback'` is set.
    - If a reply is still refused, the toggle reads "🔈 Tap to hear her", and a tap replays it.
- **Face.** On WebKit the avatar starts in **4.7–11.6 s**, measured. Past the 5 s deadline the hello went voice-only and the late face was **stopped** (the AbortErrors), so on the phone it never appeared.
  - **Fix:** a late face is shown:
    - big while she's speaking;
    - with "Tap to hear Sasha" while she's waiting for a tap, so the tap speaks through her face;
    - as the bubble once she's done.
- **Proof:** an iPhone 13 profile on Playwright WebKit 18 against production. iOS's per-element rule was emulated, because Playwright's WebKit doesn't enforce it.
  - **Before:** 3 of 3 reply lines were refused while the toggle said "Voice on". The face was lost at 11.6 s.
  - **After:**
    - The face is on screen with "Tap to hear Sasha".
    - The tap plays the hello through the face.
    - **All 3 replies were spoken** on the one primed element: 3 played, 0 refused.
  - Logs and stills are in `s232-shots/`.
  - Not yet checked on a real iPhone: the Ring/Silent switch behaviour (`audioSession` covers iOS 16.4+).

## 3 · Direct first for every kind of place
- **On /s2, for any kind of place**, the order is:
  1. their own form, or their own booking page (their booking software counts as their form);
  2. **their own WhatsApp**, drafted for the person to send from their own phone (Meta's policy, S-48 Mode A);
  3. email;
  4. phone.
- The drafted message now names the service asked for ("60-minute massage" was missing).
- **Live proofs** (scratch guest; nothing was sent):
  - Kamai Spa: their WhatsApp was drafted, with email offered as the alternative.
  - **Nail Bar Hermosilla (Treatwell):** "only takes bookings through Treatwell… I'll send their page to your phone. You then pick Sunday 11 October at 11… and book it there". She never presses Book.
  - **Dog walkers:** Dogs In Town got their WhatsApp drafted. PaseoTuPerroMadrid got "no online booking — email, or a message you send".
  - Fresha didn't come up in 2 searches (11 venues); it takes the same path as Treatwell.
  - NailOn names Booksy but doesn't link it, so it stays refused; finding its page would mean searching Booksy.
- **Not done, needs your decision:**
  - Reading a Fresha, Treatwell or Booksy page (its services, prices, open slots), deep-linking to a slot, and reading Rover's listings.
  - This conflicts with your standing rule "never probe a booking platform".
  - CR 22's own library records Fresha as "terms ban scraping; robots disallows booking paths".
  - The code keeps platforms "recognised from a link, never fetched".
  - Options: captured markup from you, a partner API, or your explicit override of the rule for named platforms.

## 4 · Pending migration (the only one: 040 and earlier are all applied)
`backend/booking_signer/sql/041_s2_memory.sql`. Apply after deploy dd3e776 (live). Until then, memory lives in the process and a redeploy forgets it. The full SQL is in the mailbox report.

## 5 · The gate's cost
- `scripts/gate_cost.py` meters every model call in the gate and prints the spend.
- **One gate run (42371b81): $1.05.**
  - Sonnet 5.5: 178 calls, $0.97. In 217k, cache write 51k, cache read 1.63M, out 24k.
  - Haiku 4.5: 64 calls, $0.08.
  - Prices are from Anthropic's pricing page: Sonnet 5.5 is $2 / $10 per million tokens (input/output), $2.50 per million for cache writes and $0.10 per million for cache reads.
- **The gate's own key is not set yet.** `SASHA_GATE_ANTHROPIC_API_KEY` is wired, but Anthropic's API can't create a key. Create one in the Console (e.g. "sasha-gate"), paste it, and the tab sets it on Railway. The log will then show its fingerprint.

## Cleanup
Scratch guest 577c2014 deleted, with 0 rows left. No real venue was contacted (no yes was given). Tyler's and Jon's accounts were not used.
