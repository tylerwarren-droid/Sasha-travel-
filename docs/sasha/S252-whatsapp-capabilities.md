# SASHA 252 · WhatsApp old flow → one brain: the capability inventory ("nothing lost")

Read-only audit of `/Users/tylerwarren/Developer/Sasha-travel-` at `sasha/252` (HEAD 3a062d5). Nothing edited, nothing run.
All paths are relative to `backend/`. "GW" = `booking_signer/guest_whatsapp.py`, "WA" = `booking_signer/wa_agent.py`,
"WB" = `booking_signer/wa_brain.py`, "AG" = `app/agent/sasha.py`, "VN" = `agapi/venues.py`, "MG" = `agapi/s2_manage.py`.

**How a message flows today (GW.turn, 743-940).** Kept in front, for everyone, before the brain/old-flow split: voice-note
transcription (746-761), opt-out/START (762-769), STOP REMINDERS / YES REMINDERS (770-775), STOP (776-781), me3 intros (792-797),
switching `back_to` / `amb:` (816-854, founder or SASHA_SWITCHING=all), products `PW.product_turn` (855), space set (856-860),
CR 13/20 hand-off sentence (868-872), secret guard (895-900). Then: `brain = WA.on(account)` (787); photo → `WA.photo_intake`
(874-878); empty/file → placeholder text (879-883); **`old_owns`** = a button whose payload matches the old flow's `pending` via
`_payload_ok` (905-909) → old flow; an invitation request (`_invite_words`, 943) → old flow; everything else → `WA.agent_turn`
(910-915). Non-brain accounts: `_answer_pending` (1953) then `_new_request` (1024), then `_reminders_offer` (924).

**Brain side.** `WA.agent_turn` (287) → `AG.turn_with_quiver(..., surface="wa")`; `surface == "wa"` is treated as `"s2"`
(AG 606-608): tools = `S2_TOOLS` (`app/agent/s2.py:58-64`) incl. HOME_TOOLS + MANAGE_TOOLS (`what_i_can_do`, `note_not_yet`,
`remember_name`, `my_plans`, `running_late`, `change_booking`, `cancel_booking`, `note_rental`, `hotel_request`) + Keep tools +
`agapi/s2_subscriptions.py` (3) + `agapi/s2_fine_print.py` (15); persona `S2.s2_system()` + `S2.WA_NOTE`. Rendering: `WA.render`
/ `WA.KIND_MAP` (229-243). Taps: `pick:<place_id>`, `say:<words>`, `yn:yes|no`, `photo:<kind>:<sid>`, `keep:yes|no` (WA 46-48,
73-86). **The brain stores its own state in `st["pending"]` as kind `"wa_agent"` (WA 51-64)** — this matters below.

Legend — Status: **✓** the brain does it · **≈** done differently / by the model's judgement, no dedicated code · **GAP** the
brain cannot do it · **FRONT** stays in front of the brain (not the old flow) · **SHARED** a helper the brain/products/other
surfaces call — must survive retirement · **n/a** brain-only (listed for completeness). Tests: **MECH** = pins old-flow
internals (can go / be rewritten); **CAP** = pins a capability that must exist after the switch.

---

## 1 · Message types (what arrives, how it's answered)

| # | Capability | Old flow: where | New brain: where | Tests (class) | Notes |
|---|---|---|---|---|---|
| 1 | Plain text request → scope gate | GW `_new_request` 1024-1119 | ✓ WA `agent_turn` 287 → AG `turn_with_quiver` | s75 `test_anything_but_booking_is_the_web_chats_turn` (MECH) | The brain is the general turn. |
| 2 | "hi/hello" → HELP text | GW `_HELP` 128, `_new_request` 1028, `help_words` 96 | ≈ WA `GREETING` 43 + recall line 314-322; else model | campusme `test_modes_switch_and_sasha_is_untouched_outside_them`, health_cr4 `NewInMadrid.test_mode_switch_and_sasha_untouched` (MECH: both assert "Tell me what to book") | Mode switching itself is FRONT and untouched; only the greeting words differ. |
| 3 | "help"/"?" → what Sasha does | GW `help_words` 96 → `agapi/s2_home.py:wa_help` 91 when brain | ✓ `what_i_can_do` + render `capabilities` (WA 180) | s249 `OneCapabilityList.test_whatsapp_words_under_the_one_brain_come_from_the_list` (CAP — already brain-aware; it pins `SASHA_WA_BRAIN=old` keeping HELP/LINKED/ONBOARD, so it changes when "old" goes) | |
| 4 | Empty message / file with no words → HELP or "Got the picture…" | GW 884-894 | ✓ GW 879-883 placeholder → brain | wa_one_brain `Routing.test_an_empty_message_and_a_file_reach_the_agent_never_help` (CAP ✓) | |
| 5 | Anything else (ideas, trip planning, questions) → web chat's brain | GW 1117 → WB `web_turn` 513 → `app/services/conductor.py` | ✓ the agent itself (`propose_trip`, `prepare_trip`, `get_trip`, …) | — | |
| 6 | Half a booking ("sort out Saturday for 2") → one question (ASK_ONE) | GW `maybe_booking` 1623, 1113 | ≈ model asks | s75 `test_sasha104_unsure_asks_one_question` (MECH) | `maybe_booking` is also used by products — SHARED (row 40). |
| 7 | "I couldn't answer that" fallback | GW 1119 | ✓ agent error line | — | |
| 8 | Password / card number never kept | GW 895-900 (G.looks_like_secret) | FRONT (runs before the brain) + WA 325 `KEEP.chat_guard` | s75 `test_a_password_is_never_kept`; wa_one_brain `test_a_password_never_reaches_the_agent` (CAP ✓) | |
| 9 | Stale open item after 2 h / greeting mid-question → "Still want X? say yes" | GW `_answer_pending` 2029-2053, `_still_want` 1927, `_open_item` 1939 | ≈ WA 304-322 (away > 6 h: recall from `s2_memory`, history restored) | — (MECH) | |
| 10 | Park & switch ("save it for later", "let me start another: …") | GW 1976-1984, 1090-1093; WB `park` 776, `start_another` 792, `save_item` 735 | ≈ memory only; no tool writes a parked item to the trip tab | — | Small GAP (see G13). |
| 11 | Typed yes / "vale" / no bound to the newest question | GW 2280-2307 (YS.is_yes) | ✓ one-yes rule: `book_venue`/`book`/`cancel_venue` need an explicit yes in a LATER turn (VN 707; `agapi/v0.py`) | s75 `test_a_typed_vale_binds_to_the_newest_question_with_its_words` (CAP ✓) | |
| 12 | A yes after 15 min places nothing | GW 2281, 2288-2291, `APPROVAL_WINDOW` 67 | ✓ `agapi.v0.stale` (VN 699) | s75 `test_a_yes_after_fifteen_minutes_places_nothing` (CAP ✓) | |
| 13 | A turn that crashes → "Something went wrong … nothing sent" | GW `_turn` 675-684 | FRONT (wraps both) | — | |
| 14 | A repeated MessageSid runs no second turn | GW `first_time` 566, `dispatch` 601 | FRONT | r1_r2 `R2NoTurnTwice` (gate) | |
| 15 | One turn at a time per number (in-process lock) | GW `_TURN_LOCKS` 539, `_turn` 676 | FRONT | — | |
| 16 | History kept (20 turns) | GW 932-934, `HISTORY_KEEP` 70 | ✓ WA `_remember_history` 396 + `s2_memory.remember` 373 | wa_one_brain `TheAgentTurn` | |

## 2 · Buttons / taps

| # | Capability | Old flow: where | New brain: where | Tests (class) | Notes |
|---|---|---|---|---|---|
| 17 | Venue card tap `pick:<nonce>:<i>` | GW `_find` 1736-1743, `_payload_ok` 2397, `_picked` 2417 | ✓ list picker `pick:<place_id>` WA `_venues` 96-107, `message_of` 74-76, `place_detail` 379 | s75 `test_a_pick_reads_the_place_and_asks_one_sentence_bound_to_its_read_back` (MECH) | |
| 18 | Typed pick: number / ordinal / name / "the one by the river" | GW `_picked` 2417-2437, `described` 2449 | ≈ model + screen state (AG `_SCREEN`, `VN.named_on_screen`) | s75 sasha104 refinements (MECH) | |
| 19 | Refine while cards show ("how about Italian in Malasaña") | GW `refine` 2354, 2083-2099 | ≈ model re-runs `search_venues` | s75 `test_sasha104_the_founders_refinements_replayed…`, `test_sasha104_a_new_area_while_choosing_moves_the_search`, `test_sasha104_a_plain_yes_while_choosing_asks_again` (MECH) | |
| 20 | `yes:/no:<id8>:<sha16>` under a read-back | GW `_ask_yes` 2896-2915 | ✓ `yn:yes/no` WA `_read_back` 124-131 | s75 `test_the_button_yes_and_a_stale_button` (MECH) | |
| 21 | `cxl:<nonce>` Cancel button under "✅ Booked" | GW `_approve` 2977-2980, 1968-1974 | ≈ no button; typed "cancel it" → `cancel_venue` | — | Cosmetic loss. |
| 22 | `lad:<nonce>:<route>` the ladder's choice (the choice IS the yes) | GW `_prepare_or_ask` 2731-2738, `_answer_pending` 1985-2016 | ✓ VN 441 `GW.ladder_of` → choose_route question; `hold_venue` `route` arg | — | |
| 23 | `where:` trip city · `am/pm/tripadd/tripkeep` gate · `oneoff/tripq` city question | WB `search` 145-161, `gate` 270-321, `city_answer` 896; GW 2017-2028 | ≈ model asks (no dedicated questions) | — (MECH) | |
| 24 | `test:/req:` hotel — TEST booking or real request | GW `_hotel_choice` 1177-1187, 2178-2188 | TEST ✓ (stays, row 63); real request **GAP** (row 64) | hotel_test_s135 | |
| 25 | A stale / foreign button → "that button was for an earlier question" | GW 1956-1958 | ✓ WA `message_of` 83-85 ("[they tapped an old … button]") | wa_one_brain `test_a_button_nothing_is_waiting_on_goes_to_the_agent` | |
| 26 | `amb:` ambiguity question, "Back to X" buttons | GW 816-854 (switching.py) | FRONT (founder / SASHA_SWITCHING=all) | — | Runs before the brain; unaffected. |
| 27 | Product buttons (`so:`, `rx:`, `hx:`, `tp:go:` …) | `products/whatsapp.py` `product_turn` 287+ | FRONT | — | |
| 28 | No quick-reply template → "(Reply: Yes · No)" text; list picker → numbered text | GW `deliver` 469-480 | SHARED (`deliver`) | — | |
| 29 | `photo:<kind>:<sid>`, `keep:yes/no`, `say:<words>` | — | n/a WA 295-299, 473, 512, 77 | wa_one_brain `Photos`, `Taps` | Brain-only. |

## 3 · Product spaces

| # | Capability | Old flow: where | New brain: where | Tests (class) | Notes |
|---|---|---|---|---|---|
| 30 | Keywords campus / relocate / españa / salud / diligence / "sasha" back | GW 855 → `products/whatsapp.py` `product_turn` 287 | FRONT | campusme, health_cr4, modes_cr15 `Words` | Kept, unchanged. |
| 31 | "tell me about RelocateMe" intro; "back to the campus tour" | GW 792-797 (me3) | FRONT | — | |
| 32 | A product hands Sasha a sentence (CR 13 "book my flights" / "a hotel in … from … to …"; CR 20 "massage near my hotel on arrival") | `products/whatsapp.py` 434-441, 509-516; GW 868-872 | ✓ the handed sentence reaches the brain (GW 870-872 run before 910) | cross_channel `BookingInsideAProduct.test_relocation_whatsapp_then_back_to_the_file`, `ConductHook.…` (MECH: patch `GW._find`); trip_cr13 ×3, move_cr35 `test_book_my_flights_saves_the_move_before_the_first_booking` (MECH: expect the old flight/hotel flows) | The brain answers it with `search_flights` / `search_stays` / `search_venues`, not travel.py cards / `_hotels`. The product's own steps (NEXT, the plan save) are product-side and FRONT. |
| 33 | Cross-device resume: account is in a space set on the laptop; "what's next for my application?" on the phone → "Back to your EX-01." | GW 1117 → WB `web_turn` 513 → `app/services/conductor.py` 2004 (`products.web.current_space`, `web_turn`) | **GAP** — AG 626-632 only adds the space as a context line; nothing routes to the product | opener_cr36 `Opener.test_web_and_whatsapp_hold_the_same_file`; web_media_cr30 `WebPhoto.test_web_and_whatsapp_hold_the_same_file`; cross_channel `Campus.test_pick_on_the_laptop_whats_next_on_the_phone` (all CAP) | See G4. |
| 34 | A bare "ad" never opens Applied Diligence over Sasha's open question; a set-aside product resumes when nothing is pending | `products/whatsapp.py` 340 (`sashas_question`), 451 (`not st.get("pending")`) | **side effect**: the brain keeps `pending = {"kind":"wa_agent"}` (WA 61-64) on every turn → products think Sasha ALWAYS has an open question | modes_cr15 `AdIsOnlyAWholeWord.test_sashas_open_question_wins_over_a_bare_ad` (CAP; pins `pending.kind == "cards"`) | See G12. |
| 35 | Space label on every reply (founder / switching) | GW 863-864, 927-931 (`SW.label_space`) | **GAP** (small) — brain path (910-915) never labels | — | Cosmetic, founder-gated. |
| 36 | One space per account kept | GW 856-860 (`products/space.py`) | FRONT + AG 626-632 reads/moves it | — | |

## 4 · Booking — venues

| # | Capability | Old flow: where | New brain: where | Tests (class) | Notes |
|---|---|---|---|---|---|
| 37 | Search → 3 cards, own/Google photos, "Sasha's pick", one-line header | GW `_find` 1669-1743, `_header` 1656 | ✓ `search_venues` (`agapi/v0.py` 457/475) + WA `_venues` 96 (up to 3 photos + list picker) | s75 `test_a_spoken_style_request_shows_three_cards_and_one_question`, `test_sasha104_the_founders_live_message_shows_cards` (MECH) | |
| 38 | "Luxury" → €€€ and up first | GW `_find` 1700-1703 | **GAP** (small) — `_search_venues` (v0 475) takes the API's order | s75 `test_sasha104_luxury_puts_three_euro_signs_first` (CAP) | |
| 39 | Name it → that venue's card, straight on to booking | GW `_find` 1679-1695 | ≈ `search_venues`/`read_booking_route` by name (model) | — | |
| 40 | Placeless search uses the active trip's city / home city | WB `placeless` 40, `context` 105, `search` 145 | ≈ model + `get_trip` / memory | — | Old detectors also feed products (`products/whatsapp.py:174-187` `for_sasha`) — SHARED. |
| 41 | A cuisine is a table, not a question | GW `CUISINE` 2463, 2510-2517 | ✓ VN `_reservation` 267-270 | s75 `test_sasha121_a_cuisine_is_a_table_not_a_question` (CAP ✓) | |
| 42 | Missing what / when / count asked one at a time | GW `_missing` 2658, `_answer_need` 2669, `_prepare_or_ask` 2703-2710 | ≈ model + `hold_venue` args (`when_invalid` VN 263-264) | — | |
| 43 | **Booking contact (name + mobile) asked on WhatsApp and saved under consent** | WB `ask_contact` 568, `_contact_answer` 579; GW 2713-2716 | **GAP** — VN 272-275 raises `contact_missing` ("ask them, once") but no tool saves the contact (`remember_name`, `agapi/s2_home.py:159`, saves a greeting name only) | s75 `test_no_contact_saved_means_no_booking` (CAP — refusal ✓; the ask/save is the gap) | See G5. |
| 44 | Route decision + its one plain line | GW `decision_of` 2621, `route_line_of` 2596, `ladder_of` 2575 | ✓ VN 441, 454 (calls the same GW functions) | — | SHARED. |
| 45 | Form route: account email in the form, read-back, yes, send, "✅ Booked … ref", their page's words | GW `_prepare_or_ask` 2755-2773, `_approve` 2949-2985 | ✓ `hold_venue` VN 280, `book_venue` → `_finish` 562 / `_book_inner` 587-596 | s75 `test_sasha117_a_form_gets_the_accounts_own_email_and_a_refusal_says_why` (CAP ✓) | |
| 46 | CAPTCHA hand-over (demo stand-in) | GW 2774-2783, `_approve` 2986-2996 | ✓ VN `_book_inner` 634-640 | — | |
| 47 | One-tap page (platform / own page) to the phone | GW `_send_link` 2534-2557 | ✓ VN 641-654 → `GW.tap_platform` 3114 | — | |
| 48 | One-tap WITH the escalation plan on one yes (page → email → call) | GW 2794-2805 (`plan_link`), 2223-2234, `PR.tap_escalation_on` | **GAP** — no `plan_line` anywhere in VN | — | Without it `auto_email_from_link` / `auto_call_from_email` never apply to brain bookings (rows 92-95). G6. |
| 49 | "BOOKED" typed after the page → recorded, then Gmail checked for the confirmation | GW 2308-2317, `watch_gmail_confirmation` 3284 | **GAP** — no tool; and see row 98 (the `link` pending is overwritten) | — | `mailbox.watch_after_link` (spawned by `tap_platform` 3137 when Gmail is connected) still runs. G3. |
| 50 | Call route: what I'll say, yes, place; "closed — I'll call at HH:MM" | GW 2830-2840, `_approve` 3010-3027 | ✓ VN 661-665 (status `scheduled` + time) | s75 `test_sasha108_calling_names_the_venue_not_the_search` (CAP ✓) | |
| 51 | **The call's result pushed to WhatsApp when it ends** (one message per state; "calling back to confirm") | GW `watch_call` 3310-3345 (spawned 3027) | **GAP** — VN 661-665 returns `placed`; nothing watches it. Only confirmation / scheduled calls are pushed (`call_routes.py:240-255` → GW `push_confirmation_result` 3365) | s75 `Progress.test_one_message_per_state_never_two` (CAP) | G2. |
| 52 | Urgent: call AND email on one yes | GW 2809-2829, `_approve` 2997-3000 | ≈ VN 483 maps `call_email` to the call only | — | Small GAP (G14). |
| 53 | Email route with a date: "Done — I've asked them" | GW 2841-2861, 3001-3009 | ✓ VN 655-660 | — | |
| 54 | **Email asking for a date and a quote** (no slot: tattoo, custom work) | GW 2862-2878 | **GAP** — `hold_venue` requires day + time (VN 260-264) | — | G7. |
| 55 | **"Whenever they have space"** (`venue_proposes`) | GW 2719, `summary` 2923, `_missing` 2662 | **GAP** — same | — | G7. |
| 56 | "Call them instead" / "email them" override | GW 2296-2302, 2318-2324 (`decide.preference`) | ✓ `hold_venue` `route` | — | |
| 57 | A matching loyalty number from the vault in the form | GW 2760-2763 (`loyalty.find_for`) | ≈ `keep_use` exists (`agapi/s2_keep.py:565`); `hold_venue` doesn't attach one | — | Small GAP (G14). |
| 58 | Rehearsal / test venue for founder-test accounts | GW `rehearsal` 1761, `TEST_CARD` 1758, 1724-1725 | ✓ S2 demo (`app/agent/s2.py:102` `demo`) — founder / SASHA_S2_DEMO_ACCOUNTS | s75 `test_sasha117_the_rehearsal_books_our_test_venue_never_a_real_one` (CAP — covered differently) | |
| 59 | "✅ Real booking — not a test" label (founder) | GW 2905-2907 | n/a (MECH) | — | |
| 60 | Booked → trip-day words + receipt line | GW `_approve` 2972-2980, `WB.trip_day_words` 426 | ✓ VN `_book_inner` 586 (`itinerary`) | — | |
| 61 | Every attempt in the outcomes ledger | GW `_outcome` 2928 | ✓ VN `_finish` 573-579 | — | |
| 62 | TEST deposit page after a Sasha Test Venue booking (`SASHA_TEST_VENUE_DEPOSIT=1`) | GW 2983-2984, `_test_deposit` 3254, `watch_deposit` 3264 | **GAP** (test-only) | — | G15. |

## 5 · Booking — hotels, flights, trips, demo spa/shop

| # | Capability | Old flow: where | New brain: where | Tests (class) | Notes |
|---|---|---|---|---|---|
| 63 | Hotel TEST booking, Stripe test pay, "🧪 … ref" when paid | GW `_hotels` 1157, `_hotel_test_ask` 1190, `_hotel_test_pay` 1205, `watch_hotel_payment` 1216 | ✓ ≈ `search_stays` (v0 427) → `hold_booking`/`book` (TEST) → render `pay` (WA 195) → `paid_watch._tell` (paid_watch.py 199) | hotel_test_s135 `OnWhatsApp.test_test_booking_paid_then_a_test_reference` (MECH — same capability, other engine) | |
| 64 | **Real request to a hotel**: its own booking engine with the dates filled; an email asking for a room for N nights; a call that says the stay (in Spanish in Spain) | GW `_hotels` 1169-1174, `_send_link` 2538-2552, 2853-2856 | **GAP** — VN has no `nights`; `hotel_request` (`agapi/s2_hotel.py:87`) is upgrade / late check-out for an existing stay | hotel_ladder_s138 `OnWhatsApp` ×2; hotel_test_s135 `test_request_from_the_hotel_is_the_real_path`, `EmailOnlyVenue.test_an_email_only_hotel_gets_the_email_route`; travel_s132 `Hotels` ×2 (CAP) | G8. |
| 65 | Flights (Duffel TEST): 3 cards, pick, read-back, Stripe TEST pay, booked when paid | GW `_flights` 1237, `_flight_pick` 1260, `_flight_approve` 1279, `watch_flight_payment` 1310 | ✓ `search_flights` (v0 400) → render `flights` (WA 110) → `choose_offer` / `hold_booking` / `book` → `pay` → `paid_watch` | travel_s132 `FlightsOnWhatsApp` ×2 (MECH — pin travel.py) | |
| 66 | Itinerary: "where am I on the 5th", "what do I have tomorrow", "when is my booking at X", "my trips", "show my trip" | GW 1049-1064 → `itinerary_q.answer` 335 | ✓ `my_plans` (MG 121, day filter `_on` 109) + render `plans`; `get_trip` | — | |
| 67 | **"Do I have time to drive / fly to X between A and B?"** (Google Routes, Duffel schedules) | `itinerary_q.time_for` 110 | **GAP** | travel_s132 `Rehearsal2.test_a_time_question_is_a_question` (CAP) | G9. |
| 68 | Trip planning (saved plan, same as the web) | WB `web_turn` 513-561 | ✓ `prepare_trip` / `propose_trip` / `get_trip` / `get_total` / `swap_stay` | — | |
| 69 | **A place picked from a trip search is added to that trip day, not booked; "book it at 8" books it** | GW 2480-2483 → WB `add_to_trip` 447, `book_added` 463 (`trip_added`) | **GAP** — no tool adds a venue to a plan day | — | G10. |
| 70 | Restaurant + spa from one sentence, both on ONE yes | GW `COMBO` 1349, 1379-1481 | **GAP** (demo) | demo_spa_s126 `test_combo_two_card_sets_one_yes_two_bookings`, `test_combo_times_each_next_to_its_own_kind` (CAP if the demo stays) | G11. |
| 71 | Kanoe Demo Spa booked with the saved vault membership (one use, logged) | GW `_spa_start` 1483-1543 | **GAP** (demo) — the Keep holds passports/loyalty, not logins | demo_spa_s126 `Spa` ×5 + `SavedAsTheVaultSavesIt` ×5 (CAP if the demo stays) | G11. |
| 72 | Kanoe Demo Market "reorder my usual" with the saved login | GW `_reorder` 1546-1579 | **GAP** (demo) | demo_shop_s121 `Reorder` ×3 (CAP if the demo stays) | G11. |
| 73 | "reset the demo" (founder, after a yes) | WB `RESET` 611, `start_reset` 713; GW 1032-1034 | ≈ founder ops route `booking_signer/demo_ops.py` (resets the same data); not by WhatsApp word | — | Small. |
| 74 | "send me the captcha test" (founder) | GW 1086-1089 (`captcha_test.asked` 13) | **GAP** (founder tool) | — | Small. |
| 75 | Engine-check answers "1 filled / 2 not filled / wrong page" (founder) | GW 2159-2177 (`engine_check`, set by hand) | **GAP** (founder ops) | hotel_ladder_s138 `EngineCheck.test_answers_are_recorded_in_order_or_by_number` (CAP for ops) | Small. |

## 6 · Manage — cancel, what's coming up, receipts, running late

| # | Capability | Old flow: where | New brain: where | Tests (class) | Notes |
|---|---|---|---|---|---|
| 76 | Cancel intent in EN/ES ("No please cancel Yatri", "anula la de Yatri"); "don't cancel" isn't | GW `cancel_intent` 962, `_CANCEL_WORD` 952, `_NOT_CANCEL` 953 | ≈ model → `cancel_venue` (VN 692) / `cancel_booking` (MG 426) | s75 `test_sasha109_the_founders_cancels`, `test_sasha117_cancel_wins_over_search_with_or_without_cards`, `test_sasha117_cancel_while_cards_show_is_a_cancellation`, `test_sasha117_the_dinner_and_the_day_are_not_the_venues_name` (CAP — behaviour now the model's) | `cancel_intent` is also read by products (`for_sasha`) — SHARED. |
| 77 | "Cancel tonight's dinner" = today's booking (a day filter, never a name) | GW `cancel_day` 976, `_cancel_find` 3462-3471 | ≈ model + `my_plans`; `cancel_venue` takes only `venue` / `trip_item_id` (VN 702-705) | s75 `test_sasha121_tonights_dinner_is_todays_booking_not_a_name` (CAP) | |
| 78 | Several bookings → numbered list; twins told apart by reference | GW `_cancel_find` 3492-3500, `cancel_pick` 2123-2134 | ≈ model + `my_plans` (refs in `venue_bookings` VN 685) | s75 `test_sasha109_several_bookings_get_a_numbered_list`, `test_sasha117_the_cancel_list_is_upcoming_only_and_tells_twins_apart` (CAP ✓ upcoming-only in VN 689) | |
| 79 | Cancel read-back + yes by its route (call, email, their link → "you press it") | GW `_cancel_row` 3504, `_cancel_approve` 3526-3560 | ✓ `cancel_venue` VN 692-719 | s75 `test_cancel_by_email_says_cancelling_never_cancelled_until_their_words` (CAP ✓ the honesty) | |
| 80 | **"X has cancelled your booking" pushed later** (a written cancel confirmed; a cancelling call's result) | GW `watch_cancel` 3563, `watch_call(..,"cancel")` 3538 | **GAP** — nothing watches; `push_confirmation_result` covers only scheduled / not-reached cancel calls (call_routes 243-244) | same test (CAP) | G2. |
| 81 | Receipts / "my bookings" / "what have I booked" | GW `_RECEIPTS` 127, `_receipts` 3447 | ✓ `my_plans` + render `plans` (WA 140-143) | s75 `test_receipts` (CAP ✓) | |
| 82 | **A forwarded / pasted venue confirmation filed on the booking** ("✅ Confirmed in writing") | GW `_forwarded_confirmation` 1582-1611 (`written.file`) | **GAP** | written_s118 `OnWhatsApp.test_3_a_forwarded_confirmation_on_whatsapp_is_filed_and_answered` (CAP); `test_a_new_request_is_never_taken_for_a_forward` (MECH) | G1. |
| 83 | Running late · change a booking · hotel upgrade · subscriptions · fine print · Keep | — | n/a `running_late` MG 204, `change_booking` 263, `hotel_request`, `find_subscriptions`…, `accident`…, `keep_*` | — | Brain-only. Note: running late's venue answer is not pushed to WhatsApp either (venue_notice.after_call). |

## 7 · Media

| # | Capability | Old flow: where | New brain: where | Tests (class) | Notes |
|---|---|---|---|---|---|
| 84 | Voice note → words (Deepgram, retries) + "🎙 I heard: …" | GW `voice_text` 687, turn 746-761 | FRONT (both) | — | |
| 85 | Voice note not made out → "send it again" | GW 887-891 | ✓ GW 882 placeholder → model asks | s75 `test_sasha104_a_voice_note_not_made_out_is_asked_again` (CAP ✓) | |
| 86 | Voice note in → voice note back | — | n/a WA 365-368, `tts_note` 583 | wa_one_brain `test_voice_in_gets_voice_out_text_in_text_out` | |
| 87 | Photo outside a space | GW 890 ("only inside EspañaMe or RelocateMe") | ✓ WA `photo_intake` 457 (passport / loyalty / statement / damage) | wa_one_brain `Photos` | Brain is a superset. |
| 88 | Photo inside a product space | `products/whatsapp.py` (media) | FRONT | web_media_cr30 | |
| 89 | PDF / other file | GW 884-894 (HELP) | ✓ placeholder → model (neither reads it) | wa_one_brain | No loss. |
| 90 | Card photos: venue's own og:image first, Google's else, cached; late photos follow; streamed cards | GW `_photo_of` 1782, `_photos_within` 1894, `_late_photos` 1904, `_stream_cards` 1855 | ≈ `VN.photos_for` (v0 493) + WA `_venues` 102-104 (up to 3 photos with the list) | perf_s140 `Cards.test_the_cards_go_within_the_budget_and_late_photos_follow`, perf_s149 `StreamedCards` (MECH) | `_photos_within` is SHARED (`app/services/world_itinerary.py:139`, VN 168). |

## 8 · Proactive (messages Sasha starts) and how their answers come back

| # | Capability | Sender / where | Reply path today (brain on) | After the switch | Tests | Notes |
|---|---|---|---|---|---|---|
| 91 | Reminders: day before / not confirmed / leave now / morning brief / written confirmation; quiet hours, 4/day, templates outside 24 h | `proactive.py` `tick` 414, `_send` 384-412 | text only; any reply → brain | ✓ unchanged | one_sasha_cr10 `Reminders` | |
| 92 | No-reply call offer ("No reply yet … Shall I call them?") | `proactive.no_reply_offers` 514 → GW `offer_no_reply_call` 3244 → `offer_escalation` 3065 (pending `no_reply_call`, `yes:<id8>:<sha16>`) | Tap → `old_owns` (GW 907) → `_answer_pending` 2235-2245 → call read-back → its tap → old `_approve` + `watch_call` | **GAP** | — | Typed "yes" goes to the brain today and is lost. G3. |
| 93 | Auto call under the yes after 24 h without an email reply | `proactive.no_reply_offers` 543-546 → GW `auto_call_from_email` 3224 | no reply needed | ✓ if kept (SHARED) — but only bookings whose read-back carried the plan (old flow only, row 48) | — | |
| 94 | Page not pressed in time → offer email / call / both | `proactive.tap_offers` 554 → GW `offer_escalation` 588 (pending `no_reply_call`) | as row 92 | **GAP** | — | `stale_links` includes brain-made links → the brain's bookings get an offer only the old flow can answer. |
| 95 | Page not pressed → email sent under the plan | `proactive.tap_offers` 579-582 → GW `auto_email_from_link` 3196 | none | ✓ if kept (old-flow bookings only) | — | |
| 96 | Gmail find offered ("Yes/No": add / confirm from their inbox) | `mailbox.sync` 538 → `_offer_on_whatsapp` 578-591 (pending `mailbox`) | Tap → `old_owns` → `_answer_pending` 2135-2142 → `/api/booking/mailbox/finds/{id}` | **GAP** | — | G3. |
| 97 | Gmail automatic update told ("✅ TheFork confirms …") | `mailbox._told_auto` 541-559 | text | ✓ | — | |
| 98 | Their page sent → "BOOKED" typed | GW `tap_platform` 3131-3134 (pending `link`) | Typed → brain; also the brain turn's own final `put_state` (GW 913) overwrites the `link` pending written mid-turn by `tap_platform` (VN 647) | **GAP** | — | G3. |
| 99 | Deposit asked on a call → "Ask them for the payment link?" | `call_routes.py:261-267` → GW `push_payment_question` 3399 (pending `payment`) | Tap → `old_owns` → `_answer_pending` 2143-2158 → `/api/booking/payments/{id}/approve` | **GAP** | — | G3. |
| 100 | Confirmation-call / scheduled-call result | `call_routes.py:240-255` → GW `push_confirmation_result` 3365 | text | ✓ (SHARED) | s75 `Progress.test_sasha108_the_confirmation_result_is_pushed_from_where_it_is_recorded` | |
| 101 | Immediate call result | GW `watch_call` 3310 (old flow only) | — | **GAP** (row 51) | s75 `Progress.test_one_message_per_state_never_two` | G2. |
| 102 | Payment result ("✅ booked (TEST) …") | `paid_watch._tell` 199-213 | text | ✓ (works for brain `book`) | r1_r2 `R1PaymentResultReachesThePhone` (gate) | |
| 103 | Tap to pay / tap to finish / their page on the phone | GW `tap_to_pay` 3092 (travel.py 342, hotel_test.py 141, basket_book.py 366/434/467), `tap_to_finish` 3141 (handover.py 679, ladder_routes.py 588, captcha_test.py 37, hotel_test.py 204), `tap_platform` 3114 (ladder_routes.py 1076, VN 647) | text / template | ✓ (SHARED) | — | |
| 104 | Hand-over finished → "✅ Booked … receipt sent" | GW `_told_handover_booked` 3671 (`handover.ON_BOOKED`) | text | ✓ (SHARED) | — | |
| 105 | Calendar reconnect · rental moments · demo ops · "Picking up: …" from the web | `calendar_sync.py:277-292`, `rental_moments.py:141-155`, `demo_ops.py:39-45`, `handoff_phone.py:41-56` | text; a reply goes to the brain | ✓ | — | "Picking up …" reads plan_store; the brain sees it only through memory/`get_trip`. |
| 106 | Products' own pushes (CampusMe watch, health / cita, relocation after) | `products/campus/watch.py:66`, `products/health/turn.py:558`, `products/health/cita.py:444`, `products/relocation/after.py:352` | text; replies → `product_turn` (FRONT) | ✓ | — | Health uses GW `watch_call` (turn.py 340, cita.py 574) — SHARED. |
| 107 | An invitee picked a time → inviter told + cards for that slot, or "Where should I look?" | `invitations._tell_inviter` 352-387 → GW `_find` (old cards `pick:<nonce>:i`) / pending `invite_where` | Card taps → `old_owns` → old flow; typed area / typed pick → brain (lost) | **GAP** (partly broken today) | — | G3. |
| 108 | Reminders offered once to a v2-consent guest ("Reply YES REMINDERS") | GW `_reminders_offer` 1006, appended 924 | never on the brain path (910-915 return before 924) | **GAP** (small) | — | G16. |

## 9 · Account, consent, window

| # | Capability | Old flow: where | New brain: where | Tests (class) | Notes |
|---|---|---|---|---|---|
| 109 | LINK 123456 (10 min, one use, 5 tries/h) | GW `dispatch` 609-624, `whatsapp_link` 3617 | FRONT | s75 `Webhook` | |
| 110 | Unknown number → one onboarding line, at most every 10 min | GW `dispatch` 657-663, `onboard_words` 112 | FRONT | s75 `Webhook.test_an_unknown_sender_gets_one_sentence…` | Tyler's decision: this replaces the automatic guest (row 111). |
| 111 | Automatic private guest account on first message (no sign-in wall) | GW `dispatch` 636-656 (`guest_accounts`, SASHA_AUTO_GUESTS) | — | — | To be removed by decision, not a gap. |
| 112 | A venue writing to the guest number → venue path, never answered | GW `dispatch` 599-600 | FRONT | s75 `Webhook` ×2 | |
| 113 | A reply from someone Sasha wrote to FOR a person (send_whatsapp) | GW `dispatch` 625-628 → `agapi/s2_whatsapp.py:165` | FRONT (unlinked senders only) | — | |
| 114 | STOP → said once, then silence; START resumes | GW turn 762-769, 776-781; `deliver` 457 | FRONT | s75 `test_stop_is_said_once_then_silence_and_start_resumes`; wa_one_brain `test_stop_still_wins` | |
| 115 | STOP REMINDERS / YES REMINDERS (consent v3) | GW `_reminders_words` 990, turn 770-775 | FRONT | — | |
| 116 | Nothing outside the 24 h window; approved templates for tap-to-pay/finish and reminders | GW `deliver` 460-462, `_tell` 3172, `TEMPLATES` 3165; `proactive._send` 404-410 | SHARED | s75 `test_outside_twenty_four_hours_nothing_is_sent` | `booking_confirmed/declined/reminder` ContentSids in GW 3167-3169 are declared but unused. |
| 117 | Unlink from the web → "Unlinked." | GW `whatsapp_unlink` 3651 | SHARED | — | |
| 118 | Invitation request ("book dinner with Jon this week") → free slots + a link to send | GW `_invite_words` 943 keeps it out of the brain (910) → `_new_request` 1081-1085 → `_invite` 1628 | FRONT by design — **but it IS old flow**: `_invite`, its `invite_window` answer (2104-2111, typed → brain today → lost), `WB.ask_contact` | — | Retiring the old flow deletes it unless kept or built (G3/G5). |
| 119 | Invitation booked by call → the invitation follows the booking | GW `_approve` 3022-3024 | **GAP** (with 118) | — | |
| 120 | Invitee opts in with "INVITE ABCD2345" / stops | GW `dispatch` 629-635 → `invitations.on_invite_message` 401, `on_invitee_stop` 414 | FRONT | — | |

## 10 · Anything else (dependencies — "retire" must mean re-routing, not deleting the module)

| # | What | Where it's used | Status |
|---|---|---|---|
| 121 | The web VOICE avatar's booking turn calls the old flow directly | `booking_signer/voice_turn.py:66-67` (`GW._answer_pending`, `GW._new_request`) | SHARED — deleting the old flow breaks the voice page, not just WhatsApp. |
| 122 | The brain's venue tools are built on GW | VN: `GW.api`, `refusal_words`, `_hours_of`, `ladder_of`, `decision_of`, `guest_lines`, `summary`, `plain_venue`, `_photos_within`, `_tell`, `tap_platform`; `agapi/s2_manage.py`, `s2_hotel.py`, `s2_tools.py` (`GW.api`) | SHARED |
| 123 | Products read the old flow's detectors / helpers | `products/whatsapp.py:174-187` (`cancel_intent`, `_RECEIPTS`, `COMBO`, `ITINERARY_Q`, `maybe_booking`); `products/trip.py:38,356` (`FLIGHT`, `HOTEL`); health `watch_call`, `NO_CONTACT`, `refusal_words`; campus `_spawn`, `api` | SHARED |
| 124 | The web card's ladder/plan words come from GW | `ladder_routes.py:116-139` (`ladder_of`, `decision_of`, `route_line_of`, `_hours_of`), 302 (`rehearsal`) | SHARED |
| 125 | Invitations build old-flow cards | `invitations.py:375-381` (`GW._find`) | old flow (row 107) |
| 126 | Hotel stays on the web | `world_itinerary.py:105-139` (`GW.api`, `_photos_within`) | SHARED |

**Count:** 126 rows; **112 are old-flow capabilities or mechanics** (rows 29, 83, 86 are brain-only; rows 121-126 are dependencies,
listed so nothing is deleted by accident).

---

## GAPS — what the new brain lacks

| G | What | How big | Where it would be built |
|---|---|---|---|
| G1 | Forwarded / pasted venue confirmation filed on its booking (row 82) | Small. `written.file` (`booking_signer/written.py`) already does the work. | A tool `file_confirmation(text)` in `agapi/s2_manage.py` (S2_TOOLS + a CAPABILITIES line in `agapi/s2_home.py`), or a deterministic pre-check in `WA.agent_turn` before the model. |
| G2 | Results pushed to WhatsApp after the turn: immediate call (booking or cancel) and written cancellation (rows 51, 80, 101) | Medium. The watchers exist (GW `watch_call` 3310, `watch_cancel` 3563). | In `VN._book_inner` (661-665) and `VN.cancel_venue` (711-715): when the account has a linked channel, start the existing watcher (awaited-safe background task, as GW `_spawn`). Better: push every call's result from `call_routes._follow_up` (one place for all surfaces). |
| G3 | **Answers to Sasha's own questions** — no-reply/tap-expired offers, Gmail finds, deposit question, "BOOKED" after a page link, invite_where / invite_window, and the invitation cards (rows 49, 92, 94, 96, 98, 99, 107, 118) | **Large / blocking.** Today the TAP works only because `old_owns` (GW 905-909) hands it to the old flow; a TYPED yes already goes to the brain and is lost; and any brain turn replaces `pending` with `{"kind":"wa_agent"}` (WA 61-64), silently dropping the open offer. Delete the old flow and all of these stop working. | (a) Move the brain's state out of `pending` (its own key in guest_wa_state) so proactive questions survive brain turns; (b) a small resolver in `WA.agent_turn`, before the model, for these pending kinds — tap OR typed yes/no — calling the same endpoints (`/api/booking/payments/{id}/approve`, `/api/booking/mailbox/finds/{id}`, `/api/booking/links/{id}/booked` + `watch_gmail_confirmation`, a call read-back via `hold_venue(route="call")`); or (c) rewrite each offer to hand the brain a tool (`answer_offer`). Until one of these, `_answer_pending` must stay for these kinds. |
| G4 | Cross-device product resume from Sasha's space ("what's next for my application?" after the laptop) (row 33) | Medium. Three tests. | In GW turn before the brain (next to 855): if `products.space.current(account)` is a product and `product_turn` declined, offer/resume it; or give the brain a `resume_space` tool. Today it works only through `WB.web_turn` → the old conductor. |
| G5 | Ask and save the booking contact (name + mobile, under the consent sentence) (row 43; also invitations, row 118) | Small–medium. A linked account without a contact can't book any venue. | A tool `save_contact(name)` (mobile = this WhatsApp number, consent shown) reusing `contacts.py` / WB `_contact_answer` 579; `contact_missing` (VN 274) tells the model to call it. |
| G6 | The escalation plan on one yes (page → email after N h → call) (rows 48, 93-95) | Medium. | `plan_line` in `VN.hold_venue` read-backs (as GW 2794-2805, 2846), so `proactive.tap_offers` / `no_reply_offers` can act on brain bookings. Otherwise brain bookings get only offers (G3). |
| G7 | Email asking for a date and a quote (no slot) and "whenever they have space" (rows 54, 55) | Small–medium. | `VN._reservation` 259-277: accept no day/time → `flow: availability` / the `quote` body of `/api/booking/emails` (as GW 2862-2878). |
| G8 | Real request to a hotel: its engine with the dates, an email for N nights, a call saying the stay (row 64) | Medium. Five tests. | `nights` in `VN.hold_venue` / `_reservation`, passed to `/api/booking/links` and `/api/booking/emails` (as GW 2538-2552, 2849-2856), plus the TEST-or-real choice in the persona. |
| G9 | "Do I have time to drive/fly to X between A and B?" (row 67) | Small. `itinerary_q.time_for` 110 exists. | A tool `time_between(text)` wrapping `itinerary_q.ask_anything`/`time_for` in `agapi/s2_manage.py`. |
| G10 | Add a found place to a trip day without booking; book it later (row 69) | Small–medium. | A tool around `WB.add_to_trip` 447 / `plan_store` in `agapi/v0.py` or `s2_manage.py`. |
| G11 | Demos: restaurant + spa on one yes; Kanoe Demo Spa membership; Kanoe Demo Market reorder (rows 70-72) | Medium; 13 tests. **Decision needed: keep the demos or retire them with the old flow.** | Vault-login tools around `demo_spa.place` 185 / `demo_shop.place` (the Keep has no logins today). |
| G12 | Products see a permanent "Sasha question" because the brain lives in `pending` (row 34) | Small, but a real side effect. | Same fix as G3(a). |
| G13 | Park & switch ("save it for later" → trip tab) (row 10) | Small. | Tool around `WB.save_item` 735. |
| G14 | Urgent call+email on one yes; loyalty number auto-attached; "luxury" €€€ first (rows 52, 57, 38) | Small each. | `VN` 483 (`call_email`), `VN.hold_venue` (`loyalty.find_for`), `v0._search_venues` 475 (price-level order). |
| G15 | Founder tools by WhatsApp word: captcha test, engine check, demo reset (rows 73-75), TEST deposit after Sasha Test Venue (row 62); space label (row 35) | Small, founder-only. | Keep as front-of-brain founder words in GW turn, or move to the ops console. |
| G16 | Reminders offered once to v2-consent guests (row 108) | Small. | Append `_reminders_offer` on the brain path too (GW 913-915). |

## Proactive replies — where the "yes" lands today and after the switch

| Question Sasha sends | Pending kind written | A TAP today (brain on) | A TYPED "yes" today | Any other message in between | After retiring the old flow |
|---|---|---|---|---|---|
| No-reply call offer (GW 3244 / 3065) | `no_reply_call` | `old_owns` → old flow → call read-back → next tap `old_owns` → `_approve` + `watch_call` ✓ | → brain → lost | brain turn replaces `pending` → offer gone | **lost** |
| Page not pressed (GW 3065 via proactive 588) | `no_reply_call` | as above ✓ | lost | lost | **lost** |
| Gmail find (mailbox 578) | `mailbox` | `old_owns` → `/mailbox/finds/{id}` ✓ | lost | lost | **lost** |
| Deposit after a call (GW 3399) | `payment` | `old_owns` → `/payments/{id}/approve` ✓ | lost | lost | **lost** |
| Their page sent (GW 3114) | `link` | no button | "BOOKED" → brain → lost; and for a brain booking the turn's final save (GW 913) already overwrote the `link` pending | lost | **lost** |
| Invitee picked a time (invitations 352) | `cards` / `invite_where` | card tap `old_owns` → old booking flow ✓ (its yes tap too) | typed pick / area → brain → lost | lost | **lost** |
| Invitation request days (GW 1634) | `invite_window` | — | typed days → brain → lost (broken today) | — | **lost** |
| Reminders, payment results, tap to pay/finish, confirmation-call results, Gmail auto-updates, hand-over booked, product pushes | none | — | a reply is an ordinary new message → brain ✓ | — | ✓ unchanged |
| Auto email / auto call under the plan (GW 3196, 3224) | none (no question) | — | — | — | ✓ if the functions stay (SHARED) — but brain bookings never carry the plan (G6) |

**Bottom line:** with the brain on for everyone and `old_owns` kept, the tapped answers to proactive questions still work, but
typed answers and any question interrupted by another message are already lost. Retiring `_answer_pending` removes even the
taps. G3 has to be built, or `_answer_pending` kept for exactly these kinds, before the old flow goes.

## The listed failing tests — MECHANIC or CAPABILITY

| Test | Class | Why |
|---|---|---|
| campusme_cr1 `OnWhatsApp.test_modes_switch_and_sasha_is_untouched_outside_them` | MECH | Asserts the old HELP sentence on "hello"; mode switching is FRONT. |
| health_cr4 `NewInMadrid.test_mode_switch_and_sasha_untouched` | MECH | Same. |
| cross_channel_cr20 `BookingInsideAProduct.test_relocation_whatsapp_then_back_to_the_file`, `ConductHook.test_relocation_whatsapp_then_back_to_the_file` | MECH (capability kept) | Patch `GW._find`; the handed sentence reaches the brain instead. Rewrite to fake `WA.agent_turn` and assert the handed sentence. |
| cross_channel_cr20 `Campus.test_pick_on_the_laptop_whats_next_on_the_phone` | **CAP** | G4. |
| opener_cr36 `Opener.test_web_and_whatsapp_hold_the_same_file`; web_media_cr30 (1) | **CAP** | G4. |
| demo_shop_s121 `Reorder` ×3; demo_spa_s126 `Spa` ×5, `SavedAsTheVaultSavesIt` ×5 | **CAP** (if the demos stay) | G11. |
| guest_whatsapp_s75 `Turns` — spoken-request cards; sasha104 founder's live message, refinements, plain yes while choosing, unsure asks one question; button yes + stale button; anything-but-booking is the web chat's | MECH | Old card/question mechanics; the brain has its own (list picker, `yn:`). |
| guest_whatsapp_s75 `Turns` — yes after 15 min; cancel by email; receipts; sasha108 calling names the venue; sasha109 founder's cancels + numbered list; sasha117 rehearsal / form email / cancel while cards / cancel list twins; sasha121 tonight's dinner + cuisine is a table; sasha104 voice note not made out; no contact | **CAP** | Mostly covered by the brain (rows 12, 41, 45, 50, 58, 76-81, 85); not covered: luxury €€€ first (G14), cancel-by-email's later push (G2), the contact ask (G5). Rewrite against the brain with a stub model. |
| guest_whatsapp_s75 `Progress` (in the gate) | **CAP** | `watch_call` one message per state → G2. |
| hotel_ladder_s138 ×3 (`OnWhatsApp` ×2, `EngineCheck`) | **CAP** | G8 (×2); G15 (engine check, founder ops). |
| hotel_test_s135 ×3 | test booking paid: MECH (brain's stays TEST); request from hotel + email-only hotel: **CAP** | G8. |
| modes_cr15 `AdIsOnlyAWholeWord.test_sashas_open_question_wins_over_a_bare_ad` | **CAP** | G12 (the brain's state in `pending`). |
| move_cr35 `Trip.test_book_my_flights_saves_the_move_before_the_first_booking`; trip_cr13 ×3 | MECH (capability kept) | Product side is FRONT; the hand-off sentence now goes to the brain (`search_flights` / `search_stays`). Rewrite to assert the handed sentence. |
| one_sasha_cr10 (2: `test_inside_relocation_…`, `test_sashas_own_question_keeps_its_answers`) | MECH | Assert `GW.ASK_ONE` and `pending.kind == "cards"`. Spaces are FRONT. |
| perf_s140 `Cards…`, perf_s149 `StreamedCards` | MECH | Old card streaming; the brain sends photos with its list. |
| s249 `OneCapabilityList.test_whatsapp_words_under_the_one_brain_come_from_the_list` | MECH | Pins the `old` branch of `help_words` / `linked_words` / `onboard_words`; the words themselves are already the brain's. |
| travel_s132 (5): `FlightsOnWhatsApp` ×2 | MECH | Brain flights covered. |
| travel_s132: `Hotels` ×2 | **CAP** | G8. |
| travel_s132: `Rehearsal2.test_a_time_question_is_a_question` | **CAP** | G9. |
| wa_one_brain `Flag.test_modes`, `Routing.test_flag_off_is_todays_path`, `test_the_button_the_old_flow_is_waiting_on_finishes_there` | MECH | Pin the flag and `old_owns`; they change with it. Keep `old_owns` (or its replacement) until G3 is built. |
| written_s118 `test_3_a_forwarded_confirmation_…` | **CAP** | G1. |
| written_s118 `test_a_new_request_is_never_taken_for_a_forward` | MECH | |

### The gate's offline WhatsApp suite (`scripts/whatsapp_suite.py`, called from `scripts/gate.py:52` as `WS.main`)

It runs 6 modules in a clean environment (SASHA_WA_BRAIN unset, so the OLD flow): `test_one_sasha_cr10`, `test_trip_cr13`,
`test_cross_channel_cr20`, `test_finder_cr35`, `test_whatsapp_r1_r2_s206`, `test_guest_whatsapp_s75`.
- **Old-flow checks:** one_sasha_cr10 (ASK_ONE / `cards` pending), trip_cr13 ×3 and cross_channel `BookingInsideAProduct`/
  `ConductHook`/`Campus` (old `_find` / web_turn), guest_whatsapp_s75 `Turns` + `Progress` (all old flow).
- **Kept-in-front checks (stay valid):** guest_whatsapp_s75 `Webhook` (link, onboarding, venue path), r1_r2 (`paid_watch` result
  to the phone; MessageSid de-duplication), finder_cr35 (health product), cross_channel `Relocation`/`Espana` (product side).
- **Mixed:** cross_channel `ItineraryIsSashas` — the product hands the question over (FRONT), Sasha's itinerary answers it (old
  `itinerary_q` today; the brain's `my_plans` after). Not in the caller's failing list; re-check after the flip.
- Flip the default to the brain and this suite fails the deploy unless the old-flow checks are rewritten (stub model / fake
  `WA.agent_turn`) in the same change.
