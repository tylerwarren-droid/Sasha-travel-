# S-72 — A Spanish +34 caller number for Spanish venues, and calls from Sasha's own number

*Sasha tab, 1 Oct 2026 (Sasha 90). Read at source: Twilio's Regulations API for Spain (the account's own
credentials), twilio.com/en-us/guidelines/es/regulatory and …/es/voice.*

## Why a Spanish number

- **Twilio, Spain voice:** a call to a Spanish number must show *"a Twilio phone number"* in +E.164. No provision
  exists for a foreign caller ID; a +44 number shown to a Madrid restaurant is unusual, and some may not pick up.
- ⚠ **Twilio, Spain voice:** *"Spanish mobile numbers can't be used for unsolicited marketing or customer service
  calls."* A booking call is neither, but **we take a geographic Madrid number (+34 91…)**, not a mobile, so the
  question never arises. SMS stays on the UK mobile (S-70), so Spanish venues still have a number to text.

## What Twilio requires (Regulations API, Spain, business; local, mobile and national are identical)

| Requirement | Satisfied by |
|---|---|
| End-user: business name | "Kanoe Technologies SL" (the tab) |
| Proof of business identity | **one document:** the AEAT *certificado de situación censal*, or the Registro Mercantil *nota simple* |
| Proof of the NIF | the same document (B23942923) |
| Proof of a business address in Spain | the same document, if it shows Calle del Padre Damián 41, 28036 Madrid. Otherwise a utility bill, tax notice or rent receipt |

Regulation SIDs: local `RN4fef079e6810dd3af0df8a94ce9ae98b`, national `RNd83160fc0b26436b067e0bf36826a803`.

⚠ **Inventory:** the API's number search answers **404 for Spain on this account**, while the UK answers. Spanish
numbers may need the bundle approved first, or a request to Twilio. The tab checks the Console and, if needed,
drafts the request.

## The founder's part: one PDF, about 3 minutes

1. 👤 **Download the AEAT *certificado de situación censal*** (sede.agenciatributaria.gob.es → Cl@ve or the company
   certificate → "Certificado de situación censal" → PDF). **It's the same PDF Meta asks for in S-71, sitting 2: one
   download serves both.**
2. 👤 **Check that it shows** "Kanoe Technologies SL", B23942923 and Calle del Padre Damián 41, 28036 Madrid.
3. 👤 **Save it as `~/Downloads/censal.pdf`** and say so in the tab. Nothing else: no Twilio login, no form.

## The tab's part (none of his time)

1. Reuse the Madrid address `AD0a4aaadb46db5e5b0544d19f7147ef98` (S-70). Create the Spanish end-user and the
   supporting document (business_registration: name, NIF, address), and upload the PDF to it.
2. Create the bundle under the local regulation and submit it. A watcher, like the UK one, follows the review.
3. On approval: buy a +34 91 Madrid number with Voice. Its voice webhook goes to Sasha's own answering
   (`/api/booking/twilio/voice`), so a venue that calls it back reaches her.
4. **Into Bland as a caller ID** (Bland's own-Twilio route: an encrypted key from the account, then the number
   imported). Set `SASHA_CALLER_ID_ES`.
5. **Code (small):** `caller_id()` takes the venue's country. A Spanish venue gets `SASHA_CALLER_ID_ES`; every other
   venue gets `SASHA_CALLER_ID` (the UK number). The read-back names the number she calls from.
6. **Proof:** the founder's own mobile as the "venue", a test call: Sasha's +34 number shows on the screen. Calls
   are on for that test only.

## Calls from Sasha's own number (the UK one, S-70)

- **Order (Sasha 79):** the live SMS proof first, then import into Bland as caller ID, then `SASHA_CALLER_ID`.
- **Status 1 Oct:** the UK bundle `BU6ac0484b86288cd4e13aefd750d6764d` is still **in review** at Twilio. A watcher
  checks every 15 minutes. Nothing is bought until it is approved.
- Until a number of Sasha's own is imported, Bland's own caller ID is used. A venue calling it back does not reach
  Sasha, so every call gives Sasha's email for any change (Sasha 74).
