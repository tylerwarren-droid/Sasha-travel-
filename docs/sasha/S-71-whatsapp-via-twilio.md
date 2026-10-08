> ⚠ **SUPERSEDED (EU 186, 8 Oct 2026)** by `docs/sasha/whatsapp-architecture.md`, which is written from the code at `41d924e`. This document is out of date (see that file's §6). Kept for history.

# S-71 — Sasha on WhatsApp, through Twilio: what the founder must do, minimised

*Sasha tab, 1 Oct 2026 (Sasha 79). It builds on S-61 (the Meta verification walk, written by the EU session) and
replaces its screens 9–12 with **Twilio's self sign-up** on Sasha's own UK number (S-70). It was read at source:
twilio.com/docs/whatsapp/self-sign-up.*

## Why through Twilio

- The number is already Twilio's (S-70), and Twilio's sign-up registers it as a WhatsApp sender.
- **That removes S-61's Meta app, system user, permanent token, app secret and Meta payment screen.** Twilio carries
  the messages through the account we already have.
- ✅ **Billing, read at source on 1 Oct 2026 (Sasha 80).** Saved raw in `docs/sasha/replies/`, sha256 below.
  - **Meta charges per message, not per conversation.** Per-conversation pricing ended on 1 July 2025. *"You are only
    charged when a template message is delivered. All non-template messages are free."* Utility templates sent inside
    an open 24-hour customer-service window are also free (https://developers.facebook.com/docs/whatsapp/pricing).
  - **Meta's rate card, effective 1 July 2026.** The market is the **recipient's** country code, so a Spanish venue
    is billed at the Spain rate. Rates are per delivered template:

    | Market | Marketing | Utility | Authentication | Service |
    |---|---|---|---|---|
    | Spain | €0.0585 | €0.0166 | €0.0166 | n/a (free) |
    | United Kingdom | €0.0526 | €0.0182 | €0.0182 | n/a (free) |

    The same rows in GBP: Spain £0.0509/£0.0144, UK £0.0458/£0.0159. In USD: Spain $0.0707/$0.0200, UK $0.0635/$0.0220.
  - **Twilio adds *"$0.005, inbound or outbound"* per message** on top, for every message, including free ones
    (https://www.twilio.com/en-us/whatsapp/pricing).
  - **What it means for Sasha:**
    - A venue's reply, and Sasha's answer inside 24 hours, cost **$0.005 each** (Twilio only).
    - Sasha writing first (Mode B) is a **utility template**: about **€0.0166 + $0.005 ≈ 2.1 cents per venue
      contacted in Spain**.
    - Marketing templates are never used.
  - Files and their sha256:
    - `2026-10-01_meta_whatsapp-rates_EUR.csv` `9b686c9a…390bf`
    - `…_GBP.csv` `6f4e17e0…191a7`
    - `…_USD.csv` `9aa0fcb6…08ffa`
    - `2026-10-01_twilio_whatsapp-pricing.html` `6f727dc0…736d0`

## Before the founder starts (the tab; none of his time)

- ✅ **`https://project.kanoe.ai/kanoe-legal`** carries the legal identity Meta's reviewer looks for: Kanoe Technologies
  SL, NIF B23942923, Calle del Padre Damián 41, 28036 Madrid, tyler@kanoe.ai, the phrase **"Sasha by Kanoe"**, and a
  link to the privacy notice. kanoe.ai itself is hosted elsewhere (Apache, at GoDaddy), so we can't edit it. This page
  is the website given to Meta.
- The UK number must be bought (S-70) and **not already on WhatsApp**. It is new, so it isn't.
- ✅ **The inbound handler takes Twilio's `whatsapp:+…` senders (Sasha 80).**
  - They arrive on the same signed `/api/booking/twilio/sms` webhook and follow exactly the SMS rules: matched to the
    last call by the bare number or its hash, read with the field checks, a stop recorded as said on WhatsApp, and
    never an automatic reply.
  - The outcome is recorded as a `whatsapp` attempt.
  - It needs **`017_inbound_whatsapp.sql`**, which widens two check constraints and changes no rows. **Not yet
    applied: it is waiting for the founder's go.** Until it is applied, a WhatsApp message is refused with a 5xx and
    Twilio retries it. SMS is unaffected.

## The founder's unavoidable steps

**Sitting 1, about 6 minutes, after the number is bought.** In his Chrome; the tab types everything that isn't his:

1. 👤 **Twilio Console → Messaging → Senders → WhatsApp senders → Create new sender**, pick the UK number, then
   **Continue with Facebook**. He **logs in to his own Facebook, with 2FA**.
2. 🖥 **Create the business portfolio** "Kanoe Technologies SL" (Tyler Warren, tyler@kanoe.ai) and its WhatsApp Business
   Account. **Display name "Sasha by Kanoe"** (S-61 §4: the fallback is "Kanoe"), category *Travel and
   transportation*, website `https://project.kanoe.ai/kanoe-legal`.
3. 👤 **Confirms the business email** (a code or link to tyler@kanoe.ai) if Meta asks.
4. 🖥 **The number's verification code: SMS.** It arrives at Sasha's own number, the inbound handler records it, and the
   tab reads it from the database and types it into Meta's popup. (Twilio's Console shows it too.) No action from him.

**Sitting 2, about 5 minutes, any time.** Meta business verification is needed before production; before it, limited
capacity. These are S-61 screens 0 and 5–8:

5. 👤 **The AEAT *Certificado de situación censal*** (Cl@ve or the company certificate → download the PDF, 3 min).
   **Check that its address reads exactly "Calle del Padre Damián 41".**
6. 🖥 **Business Settings → Security Centre → Start verification:** Spain, the legal name, and the address **exactly as
   on the certificate**; the website as above; contact method **email at @kanoe.ai** (no document needs the phone).
7. 👤 **Enters the emailed code and uploads the certificate** (2 min). Meta's review takes ○ 1–5 business days. The
   display-name review follows it.

**Total: about 11 minutes in two sittings.** No token, no secret, no card at Meta, no GoDaddy login (email is the
contact method, so domain verification is not needed).

## After approval (the tab)

- WhatsApp replies from venues land on the reservation through the same signed Twilio webhook.
- **Mode B** (Sasha writes first) needs Meta-approved **templates**. They are drafted from S-49 (disclosure first) and
  submitted through Twilio for approval. Until then, **Mode A** stands: the guest sends from their own WhatsApp
  (S-48).

## Sasha 98 · the document for Meta's verification

- **What the founder has:** the Santander *certificado de titularidad de cuenta* (Kanoe Technologies SL, NIF
  B23942923, signed, 2026-02-18; **no address**; it carries the account's IBAN, which goes only into the upload).
- **For Meta:** it proves the **legal name**. Meta also checks the **address** typed in step 6 against a document. If
  Meta asks for an address document, the AEAT *certificado de situación censal* (step 5) shows both the name and the
  address. Use that one if Meta refuses the bank certificate.
