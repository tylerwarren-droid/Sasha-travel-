# S-68 step 1 — Places pricing and terms, read at source (1 Oct 2026)

*Sasha tab. The raw pages are saved in `docs/sasha/replies/`, unedited. Quotes are under 15 words. Everything else here is
a paraphrase; the raw file is the authority.*

## Saved raw

| File (`docs/sasha/replies/2026-10-01_…`) | What it is | sha256 |
|---|---|---|
| `developers_google_com_maps_documentation_places_web-service_data-fields.html` | the SKU each field triggers | `d4bd8a4a18910a0a3d5914856b92b37cadf06c613585542cd786b01591e5e355` |
| `developers_google_com_maps_documentation_places_web-service_usage-and-billing.html` | how Places requests are billed | `74b840a2ade1f4a0fa48caffae4f0facaf9f8c93b0708628594172ea501b4d6d` |
| `developers_google_com_maps_billing-and-pricing_pricing.html` | the price list | `49d87dac325fd779befbcf7af390dbadef68c423e293344c1ab1a9c0f8aeed11` |
| `developers_google_com_maps_documentation_places_web-service_policies.html` | Places policies: attribution, caching, ranking | `b9c10dc80d58fbaaa28957f81a165d70a5aa82a42832c8d8b4d9656e11c1b7aa` |
| `cloud_google_com_maps-platform_terms_maps-service-terms.html` | Service Specific Terms (last modified 10 Jun 2026) | `776b35b2e83324d73bd0b367f8efa74a1971fb2be8d482cbcbf50be0b66c3445` |
| `cloud_google_com_maps-platform_terms.html` | Maps Platform Terms of Service (last modified 26 Aug 2026) | `66e71727892cc85b474e5276340ec93a6129ada049b0409b243a5558888784b2` |

## The SKU per field (Text Search, Places API New)

A request is billed at the **highest** tier any field in its mask belongs to.

| Tier | Fields we use or plan to use |
|---|---|
| Essentials (IDs only) | `id` |
| Pro | `displayName`, `formattedAddress`, `addressComponents`, `primaryTypeDisplayName`, `businessStatus`, **`location`** |
| Enterprise | `internationalPhoneNumber`, `nationalPhoneNumber`, `websiteUri`, **`rating`**, **`userRatingCount`**, **`priceLevel`**, **`regularOpeningHours`** |
| Enterprise + Atmosphere | **`reviews`** |

**Conclusion.** Today's `FIND_FIELDS` already reaches **Enterprise** through the phone and website fields. Step 2 adds
`rating`, `userRatingCount`, `priceLevel`, `regularOpeningHours` (Enterprise) and `location` (Pro). **The tier does not
change, so the cost per search stays the same.** The EU spec (§4) expected a higher SKU; that turns out not to be the case.
Only `reviews` (step 9, style) moves the search to **Enterprise + Atmosphere**. Step 9 should fetch them in a separate,
per-pick Place Details call, not in every search. That decision is held for step 9.
The pricing page bills "per billable event" at the highest SKU in the mask (usage-and-billing). It does **not** say in
so many words that a 20-result page counts as one event. Raising `maxResultCount` from 5 to 20 is still one HTTP
request. Step 2 confirms the billing on the Cloud console's Places usage after the first searches; until then, this
point is **unverified**.

## The terms, and what they mean for the build

1. **Attribution (policies).** Places data shown without a Google map must carry the **Google Maps logo**, or the text
   "Google Maps" where space is short. It must be clear which content comes from Google Maps.
   → Today's cards say *"from its Google listing"*. Step 8 changes this to "Google Maps" attribution on the card list.
2. **Ranking explained (policies, "recommended", Europe).** Users should learn the main factors behind a ranking, and how
   much each one weighs. → Step 8 adds a one-line "how these are ordered" under the chips, naming the chip in use, the
   ≥ 20-review rule and the tie-breaks. We re-rank Google's results, so Google's stock explainer text doesn't fit.
3. **Reviews (policies).** Each review shown must credit its author (name, avatar, profile link where available).
   → Step 9 shows no review text without its author.
4. **Caching (ToS §3.2.3(b) and the Service Terms).** Google Maps Content must not be cached, except where the Service
   Terms allow. `place_id` may be cached. → The 20 results live only in the chat response. Re-sorts happen in the
   browser over that same response, with nothing stored server-side. The guest's hotel geocode is **not** cached
   either: it is recomputed per search. That replaces the spec's "geocode once per trip, cached", which the terms don't
   allow. (The terms do exempt an address the end user typed via Autocomplete, but not one geocoded from a Place.)

## ⚠ Findings about TODAY's product, not caused by S-68 (for the founder)

**Decided, Sasha 64 (founder): the safe route now, reversibly, flagged for counsel.** What was built is listed after
the questions below.

- **A. Saved listing data.** ToS §3.2.3(a)(iii) forbids copying and saving business names, addresses or user reviews.
  Venue reads, reservations and trip items store the venue name, phone and opening periods taken from the Google
  listing, as evidence for the booking. Whether a booking record counts as "saving" here is a legal question. The
  options are to store only `place_id` plus what the venue itself told us, or to get a legal reading.
- **B. Text-to-speech.** ToS §3.2.3(a)(iv) forbids using Google Maps Content with text-to-speech services. A Sasha call
  is a TTS voice that **dials a number taken from the listing**, and the brief may **say the venue's listed name**.
  Dialling is probably not "use with TTS"; speaking the listed name might be. A safe option is for the brief never to
  speak listing text, only the guest's own words and the venue's own site.
- **C. AI style summaries (step 9).** ToS §3.2.3(c) forbids creating content from Google Maps Content. Model-made style
  tags drawn from Google **reviews** may fall under this. Tags from the venue's **own site** do not. Recommendation:
  step 9 uses the site only, unless the founder decides otherwise.

## Sasha 64 · what was done

- **A.** Venue reads are stored without listing content (`backend/booking_signer/places_terms.py`). Each listing fact
  keeps only its kind, its place and the `place_id`; the listing keeps only its `place_id`. Whenever a read is shown
  or a call is prepared, the listing is re-read from Google. A venue picked from the cards is stored under its own
  site's name (`og:site_name` or a schema.org `name`). Failing that, it is stored under the guest's words ("tattoo
  studio in Madrid"). It is never stored under the listing's name.
  The rows written before this are cleaned by `backend/booking_signer/sql/013_purge_places_content.sql`
  (22 reads, 8 calls). That file is **not applied**: the founder runs it. It was dry-run on a local Postgres, and
  every check count came back 0.
- **B.** The venue's own number is preferred. A listing number is only dialled: it is re-read at the dial and
  checked against the hash the guest approved, and a changed number is not dialled. The read-back says "on the
  number its Google Maps listing gives", without the digits. The stored record holds only
  `number_ref {place_id, sha256}`, `dialled_number = "sha256:…"` and `number_source_kind`, and Bland's answers are
  stored without the digits. The spoken parts never carried listing text, and a test now holds that.
- **C.** Step 9 builds style tags from the venue's own site only, never from Google reviews.
- The cards credit **"Google Maps"**.

## Counsel questions (A and B)

1. **Booking records (A).** Does keeping a venue's name, address or phone, taken from a Places response, *inside one
   guest's booking record* (as evidence of what was booked and where, kept for the retention period) count as
   "copy and save business names, addresses" under ToS §3.2.3(a)(iii)? Or does it fall outside, as an end user's
   transaction record, the way the Autocomplete exception treats an address the end user chose? If it falls
   outside, how long may it be kept?
2. **Derived facts (A).** Is a fact *derived* from listing content Google Maps Content too? Examples: "they open at
   10:00 on Monday", merged with the venue's own site hours, in a stored read-back line; the scheduled call time.
   Today these are stored. They are not purged, pending this answer.
3. **The hash (A/B).** May we store a sha256 of a listing phone number, so that the number dialled is provably the
   number approved? The digits themselves are not stored.
4. **Dialling (B).** Is dialling a listing's phone number through a voice-AI call service (Bland) "use of Google
   Maps Content with text-to-speech services" under ToS §3.2.3(a)(iv)? Nothing from the listing is spoken; the
   number is passed to the telephony provider only to place the call.
5. **Speaking (B).** If a guest *typed* a venue's name and it happens to equal the listing's name, may it be
   spoken? Today it is never spoken; the question decides whether the call may say "is this {name}?" to catch a
   wrong number.
6. **Ranking (S-68 step 8).** The terms recommend explaining the main ranking factors to European users. Does the
   one-line explainer we plan (the chosen sort, the ≥ 20-review rule, the tie-breaks) meet the P2B Regulation as
   applied here, or does it need a fuller page?

## Effect on the S-68 steps

- Step 2: proceed, at no extra cost per search.
- Step 3: geocode per search, not cached.
- Step 8: "Google Maps" attribution and the ranking explainer line.
- Step 9: site-only (Sasha 64, finding C); no `reviews` field, so the search stays at the Enterprise SKU.
