# S-29 — The booking vocabulary: built, proven on Psi and Getink, measured on one held-out page

**Filed:** 29 September 2026, night. **Built and tested in Applied Diligence; not committed.**

## 0. Blunt answer

- **Psi maps all six** (Data, Hora, Pessoas, Nome, Email, Telefone) and is called a **slot booking**.
- **Getink maps name, email and phone correctly** and is called a **request form**, missing date, time and
  party. It is right to say that, not a failure.
- **On a page it had never seen** (a Turkish pansiyon in Patara, found tonight): **5 of 5 present roles right**,
  and the sixth (email) correctly reported absent. ⚠ That is **one page**, not a rate.
- ⚠ **The same page shows the bigger gap is not roles.** Its booking fields sit in **no `<form>`** (submitted by
  JavaScript), so the form parser sees **nothing**. End to end today it scores 0 of 6 there.
- **A wrong role costs a "no", not a booking**, because the read-back names the field. The exception is a label
  the person cannot read (§3).

## 1. What was built (Applied Diligence, uncommitted)

| file | what |
|---|---|
| `lib/agapi/forms/booking-roles.ts` | the vocabulary. It reads a FormMap from `form-map.ts` and does **not** change `semanticOf`, so the register maps are untouched |
| `lib/agapi/forms/booking-roles.test.ts` | Psi, Getink, 20 labels across four languages, and seven traps |
| `lib/agapi/forms/fixtures/booking-roles/getinkstudio.com__2026-09-29.json` | Getink's **derived map only**. No HTML (the kind rule). A separate directory, so `form-confirmation`'s counts stay the same |
| `docs/agapi-package/MANIFEST.json`, `lib/agapi/FIXTURES.md` | the three new paths; one fixture row |

**Order of evidence:**
1. the served control type (`email`, `tel`);
2. `autocomplete`;
3. textarea means free text;
4. then the label, the posted name and the id, against an ordered rule list.

**How the rules are ordered:**
- birth date first, so a tattoo studio's age check is never filled with the booking date;
- **full name above given and family name, and person above company**;
- party before date and time;
- a bare "Name / Nome / Nombre / İsim / Ad" last, as a **person**.

Anything else is **`unknown`, never guessed**. Any required field that is unknown or not one of the six is listed
under `must_be_read_back`.

**Languages:** English, Spanish, Portuguese and Turkish in full; German, French and Italian for the common labels.

## 2. The measurements

| page | seen while writing? | roles present | right | kind |
|---|---|---|---|---|
| Psi | yes | 6 | 6 | slot_booking |
| Getink | yes | 3 (name, email, phone) | 3 | request_form: date, time and party missing, said so |
| **Patara Golden** (Turkish, held out) | **no** | 5 (Ad Soyad, Telefon, Tarih, Saat, Kişi Sayısı) | **5** | slot_booking by roles; email absent. Konaklama → `unknown`, correctly |

- **Checks:** `npm test` ALL PASS (129 files); `tsc --noEmit` 0 errors; eslint clean on the two new files.
- ⚠ **Psi and Getink cannot measure anything, because the vocabulary was written looking at them.** Patara is
  the only honest number, and n = 1.
- A second held-out page (a Spanish Jotform template) redirected to a product page and was dropped.
- **My estimate for a plain served form in these four languages: most roles right, and misses fall to
  `unknown`, not to a wrong role.** The rules are written to fail that way. A real rate needs 20–30 held-out
  forms, which is the survey's work.

**Known weaknesses:**
- A **B2B "Name"** will read as a person.
- `cell` matches inside other words (for example "Excellent").
- "Data" is also a generic word in Portuguese.
- **A language outside the list gives `unknown` for everything**, which is honest, but reaches nothing.

## 3. What a wrong guess costs

**The read-back says the venue's own label and the value going into it** (*"In their 'Kişi Sayısı' field I'll
write 4"*):
- A wrong role is **heard before the yes**. It costs a "no" and a correction, and **nothing reaches the venue**.
- The approval binds to the hash of exactly those lines, so a guess cannot change after the yes.

**Where the read-back does not protect:**
1. **A label in a language the person cannot read.** "In their 'Kişi Sayısı' field" means nothing to an English
   speaker. **Fix, small:** say the label **and** the reading, e.g. *"their 'Kişi Sayısı' field — I read it as
   party size — 4"*. Recommended before any live use.
2. **Right role, wrong format.** A text date field filled `02/10` where the venue reads `10/02` books the wrong
   day. That is **worse than a wrong role**, because it sounds right. Formats must come from what is served
   (`type=date`, placeholder, options), or else the run stops.
3. **Unknown required fields** (Getink's `_app_id`, its file and checkbox inputs). These are **stop or ask,
   never fill**. The read-back must list them.

## 4. Next, if wanted

- **Formless forms.** Treat a cluster of labelled controls next to a submit-like button as a form. Patara shows
  why this matters. It is a change to `form-map.ts`, so the register suites would gate it.
- The label-plus-reading line in the read-back.
- A held-out sample of 20–30 forms for a real rate.
