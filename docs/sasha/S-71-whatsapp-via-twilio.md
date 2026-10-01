# S-71 — Sasha on WhatsApp, through Twilio: what the founder must do, minimised

*Sasha tab, 1 Oct 2026 (Sasha 79). It builds on S-61 (the Meta verification walk, written by the EU session) and
replaces its screens 9–12 with **Twilio's self sign-up** on Sasha's own UK number (S-70). It was read at source:
twilio.com/docs/whatsapp/self-sign-up.*

## Why through Twilio

- The number is already Twilio's (S-70), and Twilio's sign-up registers it as a WhatsApp sender.
- **That removes S-61's Meta app, system user, permanent token, app secret and Meta payment screen.** Twilio carries
  the messages through the account we already have.
- ○ **Billing** is not stated on Twilio's sign-up page. Twilio's WhatsApp pricing (Twilio's fee plus Meta's,
  passed through) is the expected model, but it is **to be confirmed** before the first template is sent.

## Before the founder starts (the tab; none of his time)

- ✅ **`https://project.kanoe.ai/kanoe-legal`** carries the legal identity Meta's reviewer looks for: Kanoe Technologies
  SL, NIF B23942923, Calle del Padre Damián 41, 28036 Madrid, tyler@kanoe.ai, the phrase **"Sasha by Kanoe"**, and a
  link to the privacy notice. kanoe.ai itself is hosted elsewhere (Apache, at GoDaddy), so we can't edit it. This page
  is the website given to Meta.
- The UK number must be bought (S-70) and **not already on WhatsApp**. It is new, so it isn't.
- The inbound handler learns Twilio's `whatsapp:+…` senders before the first message: a channel value and one migration.

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
