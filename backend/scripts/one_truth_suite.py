"""Sasha 249 · THE CONSISTENCY TEST IN THE DEPLOY GATE (EU 245, docs/sasha/one-truth-spec.md §3) — T1–T15, offline (no model, no
Places, no AgAPI, no production database), in a clean process with a stripped environment (as the safety suite runs). One line per
invariant; any T with a failing test fails the gate, and so does a T with no test at all.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

T = {   # invariant → (what it holds, the test classes that hold it)
    "T1": ("badge = acting", ["tests.test_s249_identity.T1OneResolver"]),
    "T2": ("no demo leak", ["tests.test_s249_identity.T2NoDemoLeak", "tests.test_s249_identity.OneFounderDecision"]),
    "T3": ("trips belong to the actor", ["tests.test_s249_identity.T3TripsBelongToTheActor"]),
    "T4": ("one total", ["tests.test_s249_total_options.OneTotal", "tests.test_s249_total_options.TheGuardChecksTheTotalExactly",
                         "tests.test_s249_total_options.HoldBookingSaysWhenTheTotalMoved"]),
    "T5": ("one currency", ["tests.test_s249_total_options.OneRate", "tests.test_s249_total_options.OneCurrency"]),
    "T6": ("one party", ["tests.test_s249_total_options.OneParty"]),
    "T7": ("offered = bookable", ["tests.test_s249_total_options.OfferedIsBookable"]),
    "T8": ("one status", ["tests.test_s249_status_keep_caps.Decide", "tests.test_s249_status_keep_caps.EverySurfaceReadsIt",
                          "tests.test_s249_status_keep_caps.GetStatusIsTheOneSource", "tests.test_s249_status_keep_caps.TheFrontReadsIt",
                          "tests.test_s249_status_keep_caps.BasketBookingsInTheLedger"]),
    "T9": ("WhatsApp reaches the brain", ["tests.test_one_truth.T9_WhatsAppReachesTheBrain", "tests.test_wa_one_brain.Routing"]),
    "T10": ("one capability list", ["tests.test_s249_status_keep_caps.OneCapabilityList"]),
    "T11": ("one space", ["tests.test_s249d.OneSpace", "tests.test_s249d.Names"]),
    "T12": ("one route", ["tests.test_s249d.OneRoute"]),
    "T13": ("no fixed examples", ["tests.test_s249_status_keep_caps.NoFixedExamples"]),
    "T14": ("durable claims and outcomes", ["tests.test_s249d.DurableClaims", "tests.test_s249d.DurableOutcomes"]),
    # Sasha 251 · the trip's dates from the one trip record (no "evening before"), and the read-back carries the one total
    "T15": ("right dates + one total in the read-back", ["tests.test_s251_dates.RightDates", "tests.test_s251_dates.ReadBackCarriesTheTotal"]),
    # Sasha 251 · every venue booking through the one engine path (D4: the one question word for word); "under <name>" to its person
    "T16": ("one booking path + book under another name", ["tests.test_s251_one_path.OnePath", "tests.test_s251_one_path.UnderAnotherName"]),
    # Sasha 252 · G3: Sasha's own WhatsApp questions answered on the one brain — one resolver before the model, tap or typed; the
    # brain's state in its own key, so a message in between never drops the open question
    "T17": ("Sasha's own questions answered on the brain, tap or typed",
            ["tests.test_s252_g3.Payment", "tests.test_s252_g3.Mailbox", "tests.test_s252_g3.NoReplyCall",
             "tests.test_s252_g3.TheirPageSent", "tests.test_s252_g3.Invitations", "tests.test_s252_g3.TheSlot",
             "tests.test_s252_g3.ProductsSeeNoQuestionAfterABrainTurn"]),
    # Sasha 252 · EU 251 FAIL 5: things to do are places — the one place card, photos from venue.profile (ActivityCard retired)
    "T18": ("activities are places (one card, their own photos)", ["tests.test_s252_activities.ThingsToDoArePlaces"]),
    # Sasha 252 · the Trip tab's flights from the one trip record, never "ask for flights" while they're chosen
    "T19": ("the Trip tab's flights from the trip record", ["tests.test_s252_activities.TripTabReadsTheTrip"]),
    # Sasha 253 · live vs the sandbox only in client_for, by the person's mode: the gate and every scratch guest never touch live
    # Sasha 254 · AgAPI's booking rules, vendored byte-identical — every vector (R1–R14 + access) holds in Sasha's gate
    "T26": ("the booking rules: vendored byte-identical, every vector holds", ["tests.test_cr91_vendored_rules_and_invite.VendoredRules"]),
    "T23": ("a test person never touches live (the gate included)", ["tests.test_s253_gate_never_live.PersonMode",
                                                                      "tests.test_s253_gate_never_live.SuiteGuestsAreTest"]),
    # Sasha 253 · G5: a booking that needs a name and mobile asks once (with the consent), saves them on the one person record
    "T20": ("booking contact asked once and kept",
            ["tests.test_s253_contact.AskedOnceAndKept", "tests.test_s253_contact.WhatsAppThisNumber",
             "tests.test_s253_contact.OnlyWhereTheBrainIs", "tests.test_s253_contact.BrainPath"]),
    # Sasha 253 · EU S2 item 11: every time she names (departure or landing) resolves to a stored fare; a fare gone is said with
    # what's there now (stored first); a time never offered is "not one of the options", with the options
    "T21": ("every time she offers can be booked", ["tests.test_s253_offered.EveryOfferedTimeBooks",
                                                    "tests.test_s253_offered.AFareThatWentAway",
                                                    "tests.test_s253_offered.ATimeNeverOffered"]),
    # Sasha 253 · item 4 (part 1): the WhatsApp old flow's capabilities in the one brain, each capability test moved to its path
    "T22": ("the WhatsApp capabilities live in the brain",
            ["tests.test_s253_gaps.TheToolsAreTheBrains", "tests.test_s253_gaps.G1ForwardedConfirmation",
             "tests.test_s253_gaps.G2ResultsPushed", "tests.test_s253_gaps.G4RelocationOnTheBrain",
             "tests.test_s253_gaps.G4CampusOnTheBrain", "tests.test_s253_gaps.G9TimeQuestion", "tests.test_s253_gaps.G10AddToTrip",
             "tests.test_s253_gaps.G13SaveForLater", "tests.test_s253_gaps.G15OpsConsole", "tests.test_s253_gaps.G16RemindersOffer", "tests.test_s253_gaps.BookIsNeverParked"]),
    # Sasha 253 · item 4 (part 2): the old flow's VENUE capabilities in the one engine path — no slot (G7), a hotel stay on the
    # ladder (G8), a Keep loyalty number and "luxury" €€€ first (G14); old S1 untouched
    "T24": ("the venue capabilities live in the one path",
            ["tests.test_s253_venue_gaps.TheSchemaOnTheOnePath", "tests.test_s253_venue_gaps.G7NoSlot",
             "tests.test_s253_venue_gaps.G8HotelOnTheLadder", "tests.test_s253_venue_gaps.G8OnWhatsApp",
             "tests.test_s253_venue_gaps.G14Loyalty", "tests.test_s253_venue_gaps.G14Luxury",
             "tests.test_s253_venue_gaps.OldS1Untouched"]),
    # Sasha 253 · item 5 (Tyler, mailbox 807/809): every account's WhatsApp to the one brain, no switch; an unlinked number gets one
    # /you line and no guest account; STOP / reminders / spaces / invites / LINK / G3 / the demos (until G11) stay in front; the
    # old flow's capability tests moved onto the brain
    "T25": ("WhatsApp: the one brain for everyone, the old flow retired",
            ["tests.test_s253_one_brain_all.EveryAccountEveryMessage", "tests.test_s253_one_brain_all.Unlinked",
             "tests.test_s253_one_brain_all.InFront", "tests.test_s253_wa_caps.Cancel", "tests.test_s253_wa_caps.TheList",
             "tests.test_s253_wa_caps.Tonight", "tests.test_s253_wa_caps.Cuisine", "tests.test_s253_wa_caps.Receipts",
             "tests.test_s253_wa_caps.VoiceNote", "tests.test_s253_wa_caps.Rehearsal"]),
    # Sasha 254 · item 2: every venue booking chooser (/s2, WhatsApp, /next, old S1, the old flow, the sweep) asks the vendored booking
    # rules through ONE adapter (agapi/booking_decide); each rule end to end; the retired deciders and env vars read nowhere
    "T27": ("every booking decision from the one rules file",
            ["tests.test_s254_one_decider.R1ChannelOrder", "tests.test_s254_one_decider.R2TheOneQuestion",
             "tests.test_s254_one_decider.R3R4FortyEightHours", "tests.test_s254_one_decider.R4CallsOff",
             "tests.test_s254_one_decider.R6Hotel", "tests.test_s254_one_decider.R5HotelNoReplySweep",
             "tests.test_s254_one_decider.R7R8R9TheCall", "tests.test_s254_one_decider.R8DepositAsked",
             "tests.test_s254_one_decider.R10Limits", "tests.test_s254_one_decider.R10CallRoutes",
             "tests.test_s254_one_decider.R11R12", "tests.test_s254_one_decider.R13R14",
             "tests.test_s254_one_decider.AccessTest", "tests.test_s254_one_decider.AccessSendsOff",
             "tests.test_s254_one_decider.AccessOf", "tests.test_s254_one_decider.EverySurface",
             "tests.test_s254_one_decider.Retired"]),
    # Sasha 254 · item 3: "I'll handle it" live — the rules' send is AgAPI's venue.submit_booking (read-back first, sent on their yes,
    # said in her voice; not_allowed kindly with their page), and venue.booking_status feeds get_status
    "T28": ("\"I'll handle it\" sends through AgAPI, read back first, said in her voice",
            ["tests.test_s254_handle_it_live.TheSend", "tests.test_s254_handle_it_live.Live",
             "tests.test_s254_handle_it_live.TheStatus", "tests.test_s254_handle_it_live.TheRoute"]),
    # Sasha 254 · item 5: every founder / calls / mailbox / demo / real-venue / mode decision reads AgAPI's person_access record
    # (access.get, ≤ 60 s, closed on failure); no env person list is read; SASHA_SWITCHING a kill switch only
    "T29": ("access from the one record",
            ["tests.test_s254_access.TheRecordGrantsEachPower", "tests.test_s254_access.ClosedOnFailure",
             "tests.test_s254_access.TheCache", "tests.test_s254_access.WarmAtEntry", "tests.test_s254_access.TheRulesAccess",
             "tests.test_s254_access.PlatformCheckIsAFixture", "tests.test_s254_access.NoEnvListDecidesAccess",
             "tests.test_s249_identity.OneFounderDecision", "tests.test_s253_gate_never_live.PersonMode"]),
    # Sasha 254 · found on production (cee7889): the booking rules' refusal ("This account is in test mode, …") paraphrased away —
    # and dropped as a "test" disclaimer. A told say_key's sentence is in her reply, once, on every surface S2 runs (S1 off untouched)
    "T30": ("the booking rules' refusals and stops are heard in the rules' words, once",
            ["tests.test_s254_said_and_status.TheRulesWordsAreHeard"]),
    # Sasha 254 · found on production: hold_venue drew a prepared page ("It's in your bookings") and get_status said "no booking or
    # request … nothing was set up". The prepared page is on the record get_status reads: prepared, waiting for them, not booked
    "T31": ("a prepared page is on the one status: prepared, not booked — never \"nothing\"",
            ["tests.test_s254_said_and_status.OneTruthPreparedPage"]),
    # Sasha 255 · found live (EU's scoreboard, item 16): "Yes, send it." to a money-back read-back → "that wasn't a clear yes" — a stale
    # read-back (answered or expired, from an earlier conversation) caught every later yes. It belongs to its case now; an answered one
    # uses the approval AgAPI holds, or is held again — never a refusal of a clear yes
    "T32": ("a claim's yes is never refused for a stale read-back",
            ["tests.test_s255_claim_yes"]),
    # Sasha 256 · found on production: a test person asking for "Sasha Test Venue" got Google's "Sacha Restaurant". What a test person
    # can book is decided in the ONE venue search, by the person's mode (agapi/test_venues); a live person never sees or holds it
    "T33": ("the test venue in one place: found by a test person, never by a live one",
            ["tests.test_s256_test_venue"]),
    # Sasha 256 · ONE ROUTE for every family, money included: s2_fine_print / s2_subscriptions picked their own AgAPI (a test person's
    # cards, entry and activities went to live). Only agapi_route decides; named exceptions: the access record (live), an open case
    "T34": ("live vs the sandbox for every family is decided only in agapi_route, by the person",
            ["tests.test_s256_one_route"]),
    # Sasha 256 · item 3 (CR 94): a request's status is the VENUE's own answer, through venue.booking_status — confirmed / declined /
    # another time ("proposed" is never a booking: the person decides); cancel goes through venue.cancel_booking on their yes
    "T35": ("manage a booking: the venue's own answer on the one status; cancel through AgAPI on their yes",
            ["tests.test_s256_manage"]),
    # Sasha 256 · URGENT (Tyler's WhatsApp, 13 Oct 11:03): "Sasha" → travel, then a reservation request was answered by CampusMe's old
    # question (the web's own state still held it). A pending question belongs to its space: only the CURRENT space's answers
    "T36": ("a pending question belongs to its space: after a switch, a travel request reaches the brain, never the old question",
            ["tests.test_s256_space_pending"]),
    # Sasha 257 · Tyler (row 863): "a WhatsApp question took 10–15 s before any reply". Her reply not ready within 3 s → ONE short
    # rotating holding line first (never a claim, never for a fast reply) on WhatsApp, /s2 and /next — one phrasebook (voice.py)
    "T37": ("the holding line: one short line when her reply is slow, never a claim, never for a fast reply",
            ["tests.test_s257_holding"]),
    # Sasha 257 · 13 Oct ~10:40 UTC: the Anthropic credit ran out — empty replies for everyone, the gate failing 40 unrelated-looking
    # checks, nobody told. Every turn now says it plainly and the founder is emailed (once an hour); the gate's first check names it
    "T38": ("an exhausted model credit is named: a plain line to the person, the founder told, the gate stopped by name",
            ["tests.test_s257_model_credit"]),
    # Sasha 257 · a plan turn's real cause, measured on production: the plan model THEN the hotel search. The destination's hotels
    # are searched beside the model, used only for a one-city plan in the plan's own country (else after the plan, as before)
    "T39": ("a plan's hotels searched beside its model — used only when the plan stays there, in its country",
            ["tests.test_s257_plan_speed"]),
    # Sasha 258 · CR 97: on /s2 and /next "Yes, send it" IS the approval — approvals.in_app_tap, once, with the card's own hash and
    # the person's own session; no email or text to them; a stale card → its new read-back; already tapped → "already sent" + status
    "T40": ("the in-app yes: in_app_tap once with the card's hash — stale → the new card, consumed → its status, nothing emailed",
            ["tests.test_s258_in_app_yes"]),
    # Sasha 259 · rows 883/884/888: connecting Gmail is the consent; a long job is never "lost connection" (receipts fetched at once,
    # a Gmail outage said, "working" while it runs); the trip's chosen items on the one status (S2 item 12); the calendar reads the
    # same booking record as get_status
    "T41": ("the last S2 fixes: no permission question, never a false lost connection, one status with the trip, one booking record",
            ["tests.test_s259"]),
    # Sasha 260 · row 898: Tyler's 60 receipts outlasted the client's 60 s, and she offered a bank statement — a mailbox read is its own
    # job now (in the turn when quick, else on the page when read); an AgAPI that didn't answer is said as that
    "T42": ("a slow receipts read is never a statement offer: in the turn when quick, else on the page when read; an AgAPI that didn't answer said plainly",
            ["tests.test_s260"]),
    # Sasha 261 · rows 897/900: the sandbox key's budget spent → "didn't work". The one transport (agapi_route.post) names a 402 / 429 /
    # timeout / unreachable once — the founder emailed at most once an hour — and the turn says voice.outage_line by code
    "T43": ("an AgAPI outage is named: one transport, one plain line said by code, the founder told once an hour, never 'didn't work'",
            ["tests.test_s261"]),
    # Sasha 262 · row 911 (S2 items 10, 3): the read-back's one line and the trip's one total, said by code from voice.py; "Handle it"
    # on book_venue reads it back too (never "I need a clear yes first")
    "T44": ("item 10: one read-back line by code, the turn ends there; item 3: the one total said when she leaves it out",
            ["tests.test_s262"]),
    # Sasha 263 · row 914 (S2 item 10): the yes sent item 7's older booking — 262's second memory (_ASKED_ROUTE) is gone; the in-app
    # yes sends only the latest unanswered card (read_back_id + sha, in_app_tap); no card → "There's nothing waiting to send."
    "T45": ("item 10: \"Yes, send it\" sends exactly the card on screen; a prefilled form or no card → nothing sent",
            ["tests.test_s263"]),
    # Sasha 264 · Tyler's beta (14 Oct) + rows 928/929: no silence over voice.PROGRESS_S; an empty form never called filled; a platform
    # page always the card (one line, one button, its phone failure said); the payment is the trip's one figure; short, never twice;
    # the mic never shows working while deaf
    "T46": ("S2 freeze bugs: progress lines, honest form and page, the one charge, brief replies, a mic that says when it's deaf",
            ["tests.test_s264"]),
    "T47": ("S2 freeze bugs + CR 99: a mic that opens its socket, her face on every arrival, New chat in one place, the call as an act "
            "(the card is the question, the tap the approval, dialled only from call_plan), the first line at once",
            ["tests.test_s265"]),
    "T48": ("the mic is on only when it hears (a blocked site said, with its steps); she stays full size through the first exchange",
            ["tests.test_s266"]),
    "T49": ("one audio session (play-and-record) for her face, her voice and his mic — iOS never refuses the mic for a play-only page",
            ["tests.test_s267"]),
    "T50": ("her arrival in one framing (half-body still = live), off to work on his first request by code; she tries first — never "
            "\"I can't\" before a tool tried; one labelled pause that lets go of her face",
            ["tests.test_s268"]),
    "T51": ("\"call them again\" is the engine's (CR 100, booking-rules/2.1): no retry of Sasha's own; a no-answer asks the ONE question, "
            "\"try once more\" is venue.call_again under the same approval (asked twice = one call); a listing number never kept; "
            "WhatsApp verified at linking before anything is sent",
            ["tests.test_s269"]),
    "T52": ("a booking link the person hands over goes through the venue engine's ONE classifier (venue.profile link, CR 101): Kanoe's "
            "to fill → the one read-back and yes; the person's → handed over with what it is; reservable said as fact; no form or "
            "CAPTCHA of Sasha's own reading on the one path; platform reads refuse off Railway's deployed server",
            ["tests.test_s270"]),
    "T53": ("a hotel stay is the venue engine's act (CR 102): venue.prepare_booking stay{}, the R6 call that goes with the email is "
            "submit_booking's call_plan (dialled only from it), the R5 call opens only when booking_status.follow_up.due — no clock of "
            "Sasha's; her presence on /s2 is one rule: the arrival, then always the corner (never gone), its green ring and paused look",
            ["tests.test_s271"]),
    "T54": ("ONE booking record (CR 103): a Google listing goes to venue.prepare_booking once as {source listing, place_id} — never its "
            "number; submit_booking and call_again carry no call object; the number is AgAPI's at each step (call_plan; a scheduled "
            "dial asks the act again); no number on their listing now → the no-channel line and their link; no digits or hash kept",
            ["tests.test_s272"]),
    "T55": ("Tyler's demo with Jon (16 Oct): her arrival ends on its own speech-ended event, then ~0.5 s, then the corner (always in the "
            "visible viewport); the voice label and green ring are the mic actually hearing; she greets only by rule 4 (30 min quiet, "
            "a new day, news) — never mid-flow; one booking card for every account; never names or limits how a place books",
            ["tests.test_s273"]),
    "T56": ("Tyler's iPhone (16 Oct 14:48): never a greeting under her own unanswered booking question; an open page picks up a new "
            "release at a safe moment; a place card is never empty; the mic's icon, label and ring agree; a tap that starts a "
            "conversation starts listening",
            ["tests.test_s274"]),
    "T57": ("S1 measure (observation only): every turn and every booking measured one way — ids only, never content; how far a "
            "booking got and why it stopped; duplicates and actions after a cancel counted; the store never read by behaviour",
            ["tests.test_s275"]),
    "T58": ("/s2 shows AgAPI venue.discover's answer as it is (CR 106): its groups in order, its ONE pick and reason, refused → its "
            "line only, checks → their question first, a marketplace handed over (never a send); no rule of her own in her prompt",
            ["tests.test_s276"]),
    "T59": ("While she works she says so ONCE (twice at most, the second on a long wait), then the ring shows it; a payment confirmed "
            "is said first on both doors; every completed booking ends with the closing line, once, \"sent to your email\" only when "
            "it went",
            ["tests.test_s279"]),
    "T60": ("One thing on its own (Tyler's 18 Oct decision, no packages): a flight or a hotel is bookable by itself; it joins a trip only "
            "when it is part of it; propose_trip only when they ask for a trip; old S1 (parity off) as before",
            ["tests.test_s280"]),
    "T61": ("Every line she says while her face is on screen moves her lips (Face.say, through one speak()); without her live face the "
            "line is said with her in the corner, never over a still or a frozen face; the camera line only when there is a camera",
            ["tests.test_s281"]),
    "T62": ("A paid thing is booked ONLY by paid_watch.settle, from the record written before paying (it goes with its owner): no "
            "watcher books by itself, no payment is offered without its record — a trip is never written for an owner that is gone",
            ["tests.test_s282"]),
    "T63": ("The trip card says what the trip is, from the Trip view's own record; she asks whether they need flights (none assumed, "
            "none added); a page handed over is never left hanging — one question on his return, answered on its one record",
            ["tests.test_s283"]),
    "T64": ("S2 follows AgAPI's ONE booking decision (venue.profile): its say_text and its button, every route the person finishes handed "
            "over through the one hand-over path (venue.prepare_booking); never \"can't\" while AgAPI found a route",
            ["tests.test_s284"]),
    "T65": ("One WhatsApp path: a third party's WhatsApp never leaves Kanoe's number from the one path but through AgAPI (their own "
            "WhatsApp until then); a reply from a number Kanoe wrote to goes to AgAPI's one inbound op first; the person rides on prepare",
            ["tests.test_s285"]),
    "T66": ("The floor: she never asks for a link — the last resort is ONE hand-over (AgAPI's own floor, else their website, else their "
            "listing, with the way back); no string, AgAPI say_text or model line on the one path asks for a link",
            ["tests.test_s286"]),
    "T67": ("Kanoe's WhatsApp (beta), minimum involvement: only AgAPI's gate (decision.sender, the read-back) lets it leave Kanoe's "
            "number; their own words giving venue, day, time and people are the yes (sent, one line), else ONE line asks — never a detail "
            "they didn't say or confirm, never the message's text, once; any no is their own WhatsApp; no flag, list or sender of S2's own",
            ["tests.test_s287"]),
    "T68": ("Email venues, the same rule: venue.submit_booking is the one send; 287's card for every message request (their words → sent, "
            "one line; else ONE line asks); her words never name the channel; a reply that isn't clearly yes or no is never said as "
            "confirmed; every fake guest store has the real store's shape",
            ["tests.test_s288"]),
    "T69": ("A message route AgAPI decided reaches the floor only when AgAPI's own answer carries no way to send it (any wa.me link → "
            "their own WhatsApp; sender kanoe → Kanoe's card); the link-less decision is said in one warning, and AgAPI's decision "
            "(no link, no number) is kept on the booking's measure row",
            ["tests.test_s289"]),
    "T70": ("What they want to do (book · takeaway · delivery · eat now · browse) is read in ONE place from their own words and sent to "
            "venue.discover; AgAPI's options are shown as given with its own label — S2 never filters, re-ranks or adds back a place",
            ["tests.test_s291"]),
    "T71": ("A place's curated recognition is AgAPI's one sentence (credited, dated) as given — on its card and in her words — or nothing; "
            "S2 names no guide itself and never re-ranks a value ask",
            ["tests.test_s292"]),
    "T72": ("Details has their website (AgAPI's own, else their Google listing — never a URL built by S2) in a new tab, a visible "
            "Back to Sasha, and AgAPI's sources page when it gives one",
            ["tests.test_s293"]),
    "T73": ("The opening: on load ONE action (Tap to talk to Sasha · or type · her starters), nothing said before the tap; her hello says "
            "what she does; every starter is one of her chips (Sasha 295)",
            ["tests.test_s295"]),
    "T74": ("Coming back: her first words after a return pick up where they were (voice.pickup_line over her memory, read only); the "
            "corner's words are the camera line once a session, then 'Still here.' (ES 'Aquí sigo.') (Sasha 296)",
            ["tests.test_s296"]),
    "T75": ("A vague restaurant ask hears ONE question first (Something special · Good value · Takeaway / delivery), once a session, never when "
            "they already said it; each answer is AgAPI's own input (recognition first · its value ranking · its intent) (Sasha 297)",
            ["tests.test_s297"]),
    "T76": ("A booking's hand-over button always reaches the screen (her 'tap the button' is never said over none); 297's question is in "
            "Spanish when the page is (Sasha 298)",
            ["tests.test_s298"]),
    "T77": ("While a turn works, a line is said only for a step that IS running, in its own words (with the tapped venue's name), once — "
            "never a line twice; a tap's reads start at the tap; a platform card's line is said by code (Sasha 299)",
            ["tests.test_s299"]),
    "T78": ("Every booking on every route is on its trip's ONE itinerary (agapi/itinerary.py: my_plans, the Trip tab, the reminders); a "
            "change, a cancellation or 'running late' goes by the route it was booked on, on his yes — or is said plainly and nothing "
            "is sent (Sasha 300)",
            ["tests.test_s300"]),
    "T79": ("Every booking's fine print is on its ONE itinerary row: the venue's terms in their own sentences (a deadline only from "
            "the hours they stated, reminded once before it passes), and his loyalty numbers and card perks from ONE place, his Keep — "
            "masked, the last four only, never a term or a perk nobody stated (Sasha 301)",
            ["tests.test_s301"]),
    "T80": ("The fine print is said by code, word for word, never paraphrased; a term on AgAPI's record is read from the venue's words "
            "in full (never the display line's cut); a hotel stay act is a hotel, so his programme shows on it only (Sasha 302)",
            ["tests.test_s302"]),
    "T81": ("ONE gate opens and closes every avatar (HeyGen) session: only a real signed-in person's tap on /s2; closed on the server "
            "after 60 s with nobody talking, a hidden or closed tab, or a cap (his minutes, Kanoe's — server settings), one log row each "
            "(Sasha 303)",
            ["tests.test_s303"]),
    "T82": ("a booked flight is its Duffel order READ NOW (one reader, flight_manage.order_now) on My trips and the Trip tab, never the "
            "snapshot kept at booking; after a change or a cancel she says the order as it reads; ONE resolver finds the booking he "
            "means and its own source answers (Duffel, AgAPI's route) — a hotel's nights wait for AgAPI (Sasha 305)",
            ["tests.test_s305"]),
    "T83": ("a hotel stay's nights / check-in go by its own route (AgAPI CR 137) with whatever was asked — Sasha keeps no list of what a "
            "kind may change; the stay is said as AgAPI's record has it (no check-out computed); a change or cancel request calls its quote "
            "tool first, so the price, refund or read-back is said by code before any yes (Sasha 306)",
            ["tests.test_s306"]),
    "T84": ("one read-back, one yes, it goes: the read-back is the complete request (AgAPI's exact message) on one card with one button, "
            "ONE yes (tap or typed) sends it; a yes that can't go yet is said as it is (never \"tap Yes\" with nothing to tap, never a call "
            "on top); a number linked before CR 100 is confirmed once, from itself (Sasha 309)",
            ["tests.test_s309"]),
}

_RUNNER = """
import json, sys, unittest, io
out = {}
for name in sys.argv[1:]:
    suite = unittest.defaultTestLoader.loadTestsFromName(name)
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    bad = [(str(t), tb.strip().splitlines()[-1][:160]) for t, tb in res.failures + res.errors]
    out[name] = {"ran": res.testsRun, "bad": bad, "skipped": len(res.skipped)}
print("@@RESULT@@" + json.dumps(out))
"""


def main() -> int:
    names = [n for _, ns in T.values() for n in ns]
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "TZ", "TMPDIR")}
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", _RUNNER, *names], cwd=here, env=keep, capture_output=True, text=True, timeout=300)
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@RESULT@@")), None)
    print(f"ONE TRUTH — the consistency test, T1–T{len(T)} (Sasha 249; Sasha 251 · T15)", flush=True)
    if line is None:
        print(f"  ✗ the tests did not run — {(r.stderr or r.stdout)[-300:]}", flush=True)
        return 1
    res = json.loads(line[len("@@RESULT@@"):])
    failed = []
    for t, (what, ns) in T.items():
        ran = sum(res[n]["ran"] - res[n]["skipped"] for n in ns)
        bad = [b for n in ns for b in res[n]["bad"]]
        ok = ran > 0 and not bad
        if not ok:
            failed.append(t)
        print(f"  {'✓' if ok else '✗'} {t} {what} ({ran} tests)" + ("" if ok else f" — {bad[:2] if bad else 'no test ran'}"), flush=True)
    print(f"ONE TRUTH: {len(T) - len(failed)}/{len(T)} hold" + (f" — FAILED: {failed}" if failed else ""), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
