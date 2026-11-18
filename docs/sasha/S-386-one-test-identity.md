# Sasha 386 · B) test data never reaches a real person

**Found (385's proof, 17 Nov):** the TEST organiser's roster (s335-organiser@kanoe.test) held a real person's gmail address ("Jain"),
so the Yerevan test trip would have emailed its itinerary to a real person.

**EDITING THAT ONE ADDRESS WOULD BE A PATCH.** The root fix: there is now ONE test-identity source, and a recipient outside it is
refused both where it would be held and where it would be sent.

## The one source: `backend/booking_signer/test_identity.py`

| What | Where it comes from |
|---|---|
| A person's test email | `email(slug)` gives `<slug>@example.invalid`, reserved by RFC 2606/6761 and never delivered. `form_email(slug)` gives `<slug>@example.com` for web forms, which refuse `.invalid`. |
| A person's test number | `number(n)` gives `+1 <area> 555 01nn`. NANPA reserves this for fiction, and libphonenumber accepts it, so a supplier takes it too. |
| Other test numbers | `sandbox_guest(n)` is AgAPI sandbox's range that is also NANP fiction. `uk_drama(n)` is Ofcom's drama range. `au_drama(n)` is ACMA's fictional range. |
| The fictional guest every rehearsal form is filled with | `fictional_person()`, "Prueba Sasha" |
| Kanoe's own (reaches only Kanoe) | `KANOE_NUMBERS`: the Twilio sandbox sender, Sasha's own number, and Tyler's mobile (KANOE_DECISIONS 12 Nov: "Tyler's org and phone"). `KANOE_DOMAINS`: kanoe.ai and applieddiligence.com. |
| The rule | `recipient_ok(to)` decides whether a recipient comes from the source. `may_reach(account, to)` says: a live account may reach anyone; a TEST account (person_access not live) may reach only the source. |

## Where a recipient is refused

- **Held:** `groups._held` runs before every roster write: the list, the People page, the chat, and an edit. A TEST account's
  roster refuses an email or phone outside the source and says so. Nothing is stored.
- **Sent:** `live_events.send_to_person` is the one sender of a trip's message to another person: the itineraries
  (`group_report`) and the passport links (`traveller_vault`). A TEST account's message to an address outside the source is not sent,
  and is said as not sent. This also covers rosters written before 386.

## The 0b inventory: every place a test recipient was built before 386

| # | Place | Before | Now |
|---|---|---|---|
| 1 | `scripts/gate_identity.py` (the voice loop's WhatsApp numbers) | `+346…` (real Spanish mobiles) | `TI.number` |
| 2 | `scripts/flight_suite.py`, `basket_suite.py` (the scratch traveller's mobile) | `+346120000nn` | `TI.number` |
| 3 | `scripts/voice_proof.py` (the sandbox guest) | `+1 500 555 0200…0999` (not fiction) | `TI.sandbox_guest` |
| 4 | `handover.py`, `handover_guestcentric.py`, `products/campus/live.py` (the fictional guest typed into venue, hotel and university forms) | `+34600000000` / `600000000` | `TI.fictional_person()` |
| 5 | `i18n/emails` "our test addresses" (`SASHA_I18N_TEST_TO`, which allowed any address) | any address in the env | `TI.ours`: reserved names, or Kanoe's own inboxes only |
| 6 | `issue.py` non-delivering names | its own tuple | `TI.RESERVED_*` |
| 7 | `chat_store.DEMO_USER_EMAIL` | literal | `TI.form_email` |
| 8 | The roster (TEST accounts) | anything | `_held` → `TI.recipient_ok` |
| 9 | Sends to roster people | `live_events.send_email` / the vault's own `SEND` | `send_to_person` → `TI.may_reach` (the vault's second sender is deleted) |
| 10 | Test fixtures (~40 files) | Tyler's gmail, `+346…` / `+34611…` guests, `wa_id`s, `a@b.co`, `ana@x.com`, `s@k.ai`, `@example.de` … | the source; Tyler's own mobile where the person is Tyler |

**Not a recipient (out of the class):** relocation's demo applicant (`products/relocation/turn.py` DEMO) is a filled document,
the EX-15 and the health card, that is never sent anywhere.

## The class test: `backend/tests/test_s386_one_test_identity.py`

**Scope (Tyler, 18 Nov, "Persons only"):** every person identity a test or gate script builds must come from the source or be
Kanoe's own. That covers guests, travellers, roster members, organisers, WhatsApp senders, email recipients and typed contacts.
Personal mailboxes (gmail, outlook …) are refused outright.

A venue's own number is not a person. Spain, Kenya, Portugal and Vietnam have no fictional range, and a venue is reached only through
AgAPI under real_venue_sends.

- AgAPI's vendored spec vectors (`tests/fixtures/agapi_powers_vectors.json`: `jurgen@example.de`, `+34 600 000 001`) are AgAPI's to
  fix. Until then their check is an **expected failure**, and it turns into a pass the day AgAPI ships the fix.
- The booking helper's signed vectors cannot change by a byte. They are held to a stricter rule: no number in them is valid anywhere,
  and every address is reserved or Kanoe's.

## SQL FOR CHAT: the TEST organiser's existing roster (production `yjafyzywzbmhlilxhzuz`)

Found read-only on 18 Nov. All 7 rows are on the TEST organiser (owner `da29447c…`): Jain's gmail address, and six real-shaped
`+346…` mobiles. Their emails are already `lusaobras.example`.

```sql
update group_people set email = 'jain@example.invalid', updated_at = now()
  where id = '4bd849c7-624e-4595-ab60-8372f359adf3' and group_id in (select id from groups where owner_id = 'da29447c-046a-42a4-a2e2-13b16d12856e');
update group_people p set phone = v.phone, updated_at = now()
  from (values ('60f5a275-afbc-4efc-b333-8eed35baeae2'::uuid, '+12025550151'), ('e8d3ad3a-225b-48af-acf8-a1983076cee0'::uuid, '+12025550152'),
               ('48b86d52-9a7d-49c7-983f-cc986ba3ffc8'::uuid, '+12025550153'), ('d7d8f778-abdd-4733-846b-e60d33472903'::uuid, '+12025550154'),
               ('0944c2d7-3e49-45d5-ab90-6fccb63e8899'::uuid, '+12025550155'), ('ee52af71-110b-4ef5-8819-4f527e947b3a'::uuid, '+12025550156')) v(id, phone)
  where p.id = v.id and p.group_id in (select id from groups where owner_id = 'da29447c-046a-42a4-a2e2-13b16d12856e');
-- expect: 1 row, then 6 rows
```
