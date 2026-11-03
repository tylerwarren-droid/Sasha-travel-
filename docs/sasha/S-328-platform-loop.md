# Sasha 328 · The platform booking loop (CR 160), then cancel

Tyler, 3 Nov: "finish the platform booking loop (CR 160) — do all of that, then cancel".

## Root test (written before the code)

### ONE trip record

The ONE booking record for a booking AgAPI made is **AgAPI's act**:
- Sasha keeps it in `s2_memory` kind `venue_acts` (`venue_submit._remember`).
- Pointers sit beside it, never its state (`_pointer_of`): its place ID, its trip.

Everything in this ticket reads or writes that act, and nothing else:
- **My bookings.** `venue_submit.bookings` reads the act: its state, its reference, route `platform`, the platform, the person's
  answers (their area) and the cancel link. `itinerary.venue_rows` shows the same.
- **The cancel link.** The ONE Gmail reader (`booking_signer/mailbox.py sync`) matches the platform's confirmation email to that act,
  by its reference, else the venue at its time ±90 min (`venue_submit.attach_from_mail`). It keeps the link on the act as a pointer
  (`_amend`). The mailbox find records only the match (`match_basis "agapi_act"`, `facts.agapi_act`), never a second copy of the link.
  It is never offered as "Add it to your itinerary?", which would be a second trip item.
- **Cancel.** `venues.cancel_venue` → `_cancel_act` → `platform_cancel` reads the act.

The walk's stop that asked a question is an act too, because AgAPI records a failed act. It is marked `question` and My bookings
skips it: the question is on screen, and it is not a booking.

### ONE AgAPI booking path

The path is `venue.prepare_booking` → `venue.submit_booking` read-back → the person's yes → `venue.submit_booking` with the approval:
- `venue.prepare_booking` goes through `VS.prepare`, with `venues.booking_person`, the ONE person.
- The read-back is `VS.read_back`.
- The yes is `book_venue`, then `_finish` (claimed once).
- The submit is `_agapi_send` → `VS.submit` (`in_app_tap` in the app, `whatsapp_tap` on WhatsApp).

The answer to the walk's question goes down the SAME path. It is the same booking, prepared again with `answers {field: option}`,
read back, and sent. That is `venues.platform_answer` → `_finish` → `_agapi_send`.

**The ONE person.** `venues.booking_person(account, res)` builds every person dict a venue is given:
- the name and mobile, from the ONE contact record (`guest_contacts`);
- `contacts.booking_email(account)`, the ONE booking email.

The three hand-built `{"name", "phone", "email": GR.address_of(...)}` dicts in `venues.py` are gone, and so is the `_prepared` card's
own read. A test holds it: there is no `"email": await …` in `venues.py` except `booking_person`'s own line.

**The ONE booking email.** It is chosen in this order:
1. **The address they named.** Set by "use tylerwarren@gmail.com for my bookings" → `save_contact {email}` → `contacts.set_booking_email`.
   It is stored on their contact row, `guest_contacts.booking_email`. That is the same record `/you` edits; there is no second store.
2. **Their linked Gmail's address.** `mailbox.address_of`: Gmail's own profile, read once and kept on `mailbox_links.address`. This is
   where Sasha reads, so the confirmation and its cancel link land where she can attach them.
3. **Their sign-in address.** `guest_receipt.address_of`, as before.

**The ONE question path.** The walk's question uses the card the call question already uses (Sasha 265, the CR 99 one-question card):
- `status awaiting_yes` + `ask` + `choices` + `read_back_id`;
- S2 draws it as `CallCard`; a tap goes through `sasha.card_tap` → `venues.answer_card`;
- WhatsApp draws the same event with the options as its reply buttons, or a list when there are more than 3 (`wa_agent._read_back`).

No new card kind and no frontend change. Its options are `pick:<option>` routes, exactly AgAPI's.

### Second copies: PATCH

**PATCH: `venue_truth.prepare`, a second caller of `venue.prepare_booking`.** It predates this ticket: Sasha 248/284, on the
venue_truth family's transport. The "fill it now" hand-over still calls it.
- **Why not removed here.** It is the hand-over path every platform and own-page venue uses today (Sasha 316's tests pin it). Moving it
  onto `VS.prepare` changes which AgAPI transport and which end user prepare those bookings, and that is its own change.
- **What 328 does to contain it.**
  - Its person comes from the same `booking_person` fields (the `_prepared` card's Name / Mobile / Email).
  - On a platform venue the booking is now prepared ONCE, by `VS.prepare` in `_platform_book`. That prepared booking is handed to the
    hand-over (`held["prep"]`), so `venue_truth.prepare` is not called a second time for it.
- **The test.** `test_prepare_booking_has_one_sender_and_one_named_patch` fails if a THIRD caller appears.

**PATCH: reading AgAPI's sentence for the options.** AgAPI gives the stop's why as structure (`hand_over.why == "choice"`). The field
and its options exist only inside the fixed sentence `platform_form.walk` writes: "Their booking asks for {name}: {a}, {b}, … Which
one?".
- `venue_submit.choice_of` is the ONE place that reads it. A test fails if the sentence is parsed anywhere else.
- An option whose own text contains ", " would be split wrongly.
- Structured options are AgAPI's to add (the CR below).

**PATCH: until AgAPI's walk reads `answers`, the answer is sent but the walk stops again.** Sasha sends
`{"answers": {"Zona": "Terraza"}}` to `venue.prepare_booking`, and the tests prove the body. But AgAPI's `_send_platform` fills the
select from `data["choices"]`, and nothing in AgAPI sets it.
- So today the second walk stops on the same question.
- Sasha does NOT ask twice, which would be a loop. She says "Their booking still asks for Zona after I gave Terraza, so I stopped
  before Book — nothing is booked. Their page has your details ready." and gives their page (`AskedOnceNeverALoop`).

### The whole class impossible, with a test (`backend/tests/test_s328.py`, `TheWholeClass`)

| Test | What it holds |
|---|---|
| `test_one_person_for_every_venue` | No venue person is built outside `booking_person`. Every `VS.prepare(ctx.account, place, person…)` call site is preceded by `person = await booking_person(...)`. |
| `test_prepare_booking_has_one_sender_and_one_named_patch` | `venue.prepare_booking` is sent only from `venue_submit.py` and the named PATCH, `venue_truth.py`. |
| `test_the_walks_sentence_is_read_in_one_place` | AgAPI's sentence is parsed only in `venue_submit.py`. |
| `test_the_cancel_link_is_kept_only_on_the_act` | The cancel link is written only by `venue_submit.py`. |
| `test_the_platform_cancel_sends_nothing` | The platform cancel calls no submit, read-back, claim, AgAPI or tell. |

## What was built

### 1. The walk's question, asked once

**Entry.** `follow()` runs on AgAPI's decision, route `platform`, which venue.profile gave without the person.
- `_platform_book` prepares the booking WITH the person.
- If AgAPI decides `platform_book`, the person is in the beta: the read-back is held for their yes. The card's ask is the usual
  `READ_BACK_ASK`; `what_happens` is AgAPI's "I'll fill in their booking and press Book for you."
- Anyone else gets the same prepared booking as the hand-over.

**The yes.** `_agapi_send` → `VS.submit`.
- **Booked:** handled by `_platform_result`.
- **Failed with the choice stop:** handled by `_platform_question`. The question is AgAPI's own sentence ("Their booking asks for Zona:
  Terraza, Salón, Barra. Which one?") with the options as taps, exactly AgAPI's. It is held 15 minutes.

**The answer.**
- **A tap** (`answer_card(..., "pick:Terraza")`), or their words naming exactly ONE option (`book_venue` / `hold_venue`, "salon please"
  → Salón), goes to `platform_answer`.
- **Words that name no option** never get a guess. `book_venue` raises `which_option` and the question stands.
- `platform_answer` prepares again with `answers {"Zona": "Terraza"}`, then reads back.

**When the answer sends.** The tap or answer IS the yes only when all of these hold:
- it comes from the app (`VS.TAP`) or their verified WhatsApp (`VS.WA`);
- the new read-back's words are exactly the words they already said yes to (`_same_words`, Sasha 236's rule);
- the claim succeeds. It is claimed once with `claim_words`, Sasha 314's one-instruction rule.

Otherwise the new read-back, with "Zona: Terraza" on it, is shown and their next yes sends it. Voice and old S1 always get the
read-back. Nothing bypasses the read-back → yes rule.

### 2. The booking email

`save_contact {email}` takes the address only as they wrote it this turn, and stores it on their contact row.
- **With no contact row yet:** `contact_first`. The name and mobile are asked once, then all three are saved together.
- **The mailbox's own address:** read at connect, and at the first sync for a link made before 328. It is cleared on reconnect, since a
  new mailbox may have a new address.
- **sql/047** adds `guest_contacts.booking_email` and `mailbox_links.address`, both nullable.
- **Until 047 is applied:**
  - saving a booking email is refused and says so: "couldn't be saved — nothing was saved";
  - the mailbox address isn't kept (logged);
  - every booking uses the sign-in address, as before.

### 3. After the press

**What she says.** One line, said by code where they asked. In the app it is the turn's answer (`yes_line` adds the calendar question);
on WhatsApp it is the WhatsApp turn's answer. Sasha 326: a booking pressed in this turn is that turn's answer, not a later outcome, so
`channel.tell` is not used for it.

Example: "✅ Booked: La Taberna, Friday 13 November at 21:00, 2 people, Terraza — reference CM48213."
- It carries the venue, day, time, people, area and reference.
- It never names the platform (rule 249).

**My bookings.** The act shows with its reference.

**The confirmation email.** When CoverManager's confirmation arrives, its cancel link is attached to that act:
- https only;
- on the platform's own host (the sender's platform domain or a subdomain of it);
- named as a cancel, in its path or in the words just before it.

### 4. Cancel

"Cancel La Taberna", or "cancel it" with its act_id, on a `route: platform` act goes to `platform_cancel`, which sends nothing:
- **With the email in:** "I can't cancel La Taberna for you yet — their own cancel link is below, or call them on +34 …. Nothing was
  sent." The `Cancel on CoverManager` button is their link.
- **Before the email:** "… their confirmation email with its cancel link hasn't reached your Gmail — call them on …".

The phone is the venue card's, shown at that moment and never kept (row 942). Nothing goes to AgAPI's `venue.cancel_booking`.

## The AgAPI CR this needs (AgAPI is read-only for Sasha)

**CR (proposed): "the platform walk reads the person's answers".**

1. **`venue.prepare_booking` keeps `answers` for the platform walk.** In `venue.py` `prepare()`, when `platform and data.get("platform")`
   (CR 160's `data.update(platform_page=…, contact=…)`), also set `data["choices"] = answers or {}`. That is the input's "the ONE
   question's answers", `inp["answers"]`, a dict of label → value, the same object CR 107 uses for a venue's own form.
   `_send_platform` already reads `data.get("choices")` into `b["choices"]`, and `platform_form.walk` already fills a select from it.
   One line.
2. **The stop carries its question as structure.** When `platform_form.walk` raises `Stop("choice", …)`, return
   `{"field": name, "options": [t for _, t in real[:12]], "want": want}` with the stop. `_send_platform` / `venue.submit_booking` should
   put it on the result, for example `hand_over: {link, copy, why: "choice", question: {field, options}}`, and the same on
   `venue.booking_status` for that act. Sasha then reads `question.options` and stops parsing the sentence (`venue_submit.choice_of`
   keeps the sentence only as a fallback).
3. **Later: `venue.cancel_booking` for a `platform_book` act.** Cancel on the platform's own page with the person's approval, or return
   the confirmation's cancel link from `venue.confirmation` (CR 110's reader). Until then Sasha gives the link from the person's Gmail.

## Proof

`cd backend && python3 -m unittest tests.test_s328 -v`. Offline: AgAPI, Gmail, the stores and the model are stood in.

| Class | What it proves |
|---|---|
| `TheZonaQuestion` | The Zona stop becomes taps, exactly AgAPI's options. `prepare_booking`'s body after the tap carries `"answers": {"Zona": "Terraza"}`. The booked line, My bookings with the reference, and the WhatsApp buttons. |
| `TheTapIsTheYesOnlyForTheSameWords` | A changed read-back waits for their yes; voice never takes the tap as the yes. |
| `AskedOnceNeverALoop` | The walk stopping again after the answer is said, never asked twice. |
| `TheConfirmationEmailAndCancel` | The Spanish CoverManager email puts its cancel link on that act, with no "add" offer and no second item. Only https links on the platform's own host count. "Cancel La Taberna" / "cancel it" give the link and the phone, and nothing is sent. |
| `TheBookingEmail` | "use tylerwarren@gmail.com for my bookings" is stored on the ONE contact row and is `prepare_booking`'s `person.email`. Never an address they didn't write. The default is the linked mailbox's address, then the sign-in address. |
| `TheWholeClass` | See the table above. |
