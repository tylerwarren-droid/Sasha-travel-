# DIVE · the switch-on list for rehearsal day

*CR 66. Docs only: nothing was changed or switched on to write this. Today DIVE sends **0 real messages**.*

Two things become real on rehearsal day:

- **The boat's WhatsApp** to Jon's phone: 2 messages in, 2 replies out.
- **The gear shop's email** to an inbox we own.

Below is exactly what you provide, in order, with direct links. Wherever a key or secret is involved, **you paste it
into Railway yourself**. Never paste it in chat or in a message to a tab.

Where the keys go (DIVE's own settings on Railway):
https://railway.com/project/8d53b07a-eff6-4206-98b1-220a67a2915a/service/bd0252c7-4168-4719-b8d5-09d7e51b6640/variables

---

## 1 · The real WhatsApp to Jon's phone

### Can Sasha's existing number be used? **No. A second number is needed.**

Sasha's number is +44 7915 914215, "KANOE", on Twilio. It can't be reused, for three reasons:

1. **Jon's replies would land in Sasha, not DIVE.**
   - A WhatsApp number has exactly one "a message came in" address. Sasha's is her own webhook
     (`/api/booking/twilio/sms`), which files every reply into her venue pipeline.
   - Jon's "ΝΑΙ" would go there, and DIVE would never see it.
   - Sending it on to DIVE means changing Sasha's inbound code. The isolation rule forbids that ("DIVE must not touch S1,
     S2 or Sasha").
2. **The boat would see "KANOE" as the sender**, not the operator, on a booking request in Blue Kyma's name.
3. **Twilio's shared test number (+1 415 523 8886) is taken as well.** On Sasha's Twilio account it is already wired
   to Sasha's guest service, with the same one-webhook problem.

### Two ways to get the second number

| | **A · A separate Twilio account with its own WhatsApp Sandbox** (recommended for rehearsal day) | **B · A real WhatsApp sender on Kanoe's existing Meta business** (for a real partner pilot) |
|---|---|---|
| What Jon sees | Twilio's shared sandbox number, +1 415 523 8886 | A number of our own, with a display name such as "Kanoe Demo" |
| Meta setup | **None** | A new sender under Kanoe's already-verified Meta business, plus Meta's display-name review |
| Time | About 15 minutes | Usually 1 to 2 days: a number, the sender sign-up, Meta's review |
| Cost | Free (sandbox) | A Twilio number (a few dollars a month) plus per-message fees |
| Catch | Jon must send "join …" first, and the sandbox forgets him after 3 days | A fictional name like "Blue Kyma" is likely to be refused as a display name: it must relate to Kanoe's business |

**Steps for A, in order:**

1. **Create a separate Twilio account for DIVE.** You do this; I never create accounts.
   - Sign up at https://www.twilio.com/try-twilio with an email that is **not** Sasha's.
   - It must not be a subaccount of Sasha's account: DIVE needs its own WhatsApp Sandbox and its own webhook.
2. **Open its WhatsApp Sandbox.**
   - Go to https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
   - Note the join phrase it shows (two words: "join something-something").
3. **Jon joins from his phone.**
   - He sends that join phrase to **+1 415 523 8886** on WhatsApp.
   - This also opens the 24-hour window for free-text messages (see "The 24-hour rule" below).
4. **Point the sandbox's "When a message comes in" at DIVE.** This is on the sandbox's settings tab:
   https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox
   - Set it to `https://agapi-dive-demo-production.up.railway.app/hooks/twilio/whatsapp`, method POST.
   - **This address is not built yet.** See "Still to build" below.
5. **Put the new account's two keys on DIVE's Railway variables** (the link at the top). You paste them; never in chat:
   - `DIVE_TWILIO_ACCOUNT_SID` = the Account SID (on the account's home page, https://console.twilio.com)
   - `DIVE_TWILIO_AUTH_TOKEN` = the Auth Token (same page; click to reveal)
   - `DIVE_WHATSAPP_ALLOW` = Jon's number in international format, for example `+3069…`. DIVE will refuse to WhatsApp any
     other number.
6. **Tell the CR tab "go for WhatsApp on <the rehearsal date>".** Only then is `DIVE_REAL_WHATSAPP=1` set.

**Steps for B, in order** (only when there's a real pilot):

1. Do step 1 of A: the separate Twilio account.
2. Buy a number that can receive a text or a call for Meta's code. In that account:
   https://console.twilio.com/us1/develop/phone-numbers/manage/search
3. Create the WhatsApp sender: https://console.twilio.com/us1/develop/sms/senders/whatsapp-senders →
   **Create new sender** → pick the number → **Continue with Facebook**.
   - Log in, choose **Kanoe's existing business portfolio** (already verified for Sasha), then a **new** WhatsApp
     Business Account for DIVE, so Sasha's quality rating is never shared.
4. Set the display name, e.g. "Kanoe Demo". Meta reviews it, which usually takes hours, up to 2 days.
5. Approve the first-contact template again for this account. Templates belong to a WhatsApp Business Account, so the
   one Sasha has doesn't carry over.
   - This is only needed if DIVE ever writes to a supplier who hasn't written first.
6. Steps 4 to 6 of A, with the sender's webhook instead of the sandbox's.

### The 24-hour rule (both A and B)

- Free text, such as the booking request in Greek, can only be sent within **24 hours of Jon's last message**.
- **"The day before" is only safe if it's less than 24 hours before the run.** Have Jon send "hi" on the **morning of
  the run** (and again on demo day).
- In the demo itself Jon gets **2** messages (the verification and the booking request) and sends **2** (YES and ΝΑΙ).
  Nothing goes to anyone else.

---

## 2 · The real gear email

**Already built:** DIVE sends the gear shop's email for real only when all three of these are true:

- a sending key is set;
- a "from" address is set;
- the address it's going to is on the allow-list.

Otherwise it captures the email and says so. Today none of the three is set, so 0 emails go out.

### What you provide, in order

1. **A sending domain for DIVE, in a separate Resend account.**
   - Sasha already sends from `booking.kanoe.ai`, and Resend delivers every reply received on her account to her own
     webhook (`/api/booking/email/inbound`).
   - Sharing her account would mix the gear shop's replies into Sasha's mail, and Sasha's guests' replies into DIVE's.
     That breaks the isolation rule.
   - So: sign up for a separate Resend account (https://resend.com/signup; you do this), then add a **new subdomain**
     there, for example `dive.kanoe.ai`, at https://resend.com/domains → **Add domain**.
   - Resend shows DNS records (for sending, plus an MX record for receiving). Add them at kanoe.ai's DNS provider.
     **Nothing about demo.kanoe.ai changes:** these are new records for a new subdomain only.
   - Wait for **Verified**, usually minutes.
2. **The sending key.** At https://resend.com/api-keys → **Create API key**:
   - permission **Sending access**, domain `dive.kanoe.ai`;
   - paste it into DIVE's Railway variables (the link at the top) as `DIVE_RESEND_API_KEY`;
   - also set `DIVE_EMAIL_FROM` = `Blue Kyma Diving (demo) <bookings@dive.kanoe.ai>`.
3. **The allow-listed inbox: the gear shop's mailbox.**
   - Use a mailbox **we own** that you can open on the second screen. Not the founder's own mailbox, and never a real
     business.
   - A fresh address made for the demo is best (for example a new Gmail you create).
   - Set `DIVE_EMAIL_ALLOW` = that address. DIVE refuses to email anything else for real.
4. **The inbound reply webhook**, so the gear shop's "YES" reaches DIVE:
   - At https://resend.com/webhooks → **Add endpoint**:
     - URL `https://agapi-dive-demo-production.up.railway.app/hooks/resend/inbound`
     - event **email.received**
   - Copy its signing secret into DIVE's Railway variables as `DIVE_RESEND_WEBHOOK_SECRET`.
   - **This address is not built yet.** See "Still to build" below.
5. **Tell the CR tab "go for the gear email"**, with the date.

---

## Still to build (the CR tab, about 1 day, after your go — not started)

As CR 66 asked, nothing below was built or switched on.

| Piece | Why |
|---|---|
| DIVE's own WhatsApp sender | Today DIVE's WhatsApp goes through the AgAPI sandbox, which never sends; that's how 0 real messages is guaranteed. The real send is a Twilio call from DIVE with the new account's keys, only to `DIVE_WHATSAPP_ALLOW`, only when `DIVE_REAL_WHATSAPP=1`. |
| `/hooks/twilio/whatsapp` | Receives Jon's replies, checks Twilio's signature, and files the reply on the waiting leg or verification. It is the same reply path the test drawer uses today. |
| `/hooks/resend/inbound` | Receives the gear shop's reply, checks Resend's signature, and matches it to the leg by its reply address. |
| The fake site's contacts | Today the fake Blue Kyma site lists made-up contacts (`gear@kyma-gear.example` and a test boat number). On the day it must list Jon's number and the allow-listed inbox. They will come from Railway variables, not from code. |
| A dry run with real keys and 0 sends | First every gate is checked with the allow-lists empty. Then one real message each, on rehearsal day only. |

## Your checklist

- [ ] A or B for WhatsApp (A recommended), and the rehearsal date
- [ ] The separate Twilio account, its two keys on Railway, Jon's number as `DIVE_WHATSAPP_ALLOW`
- [ ] Jon joins the sandbox (A), and says "hi" the morning of each run
- [ ] The separate Resend account, `dive.kanoe.ai` verified, the sending key and the from address on Railway
- [ ] The gear inbox we own, as `DIVE_EMAIL_ALLOW`
- [ ] The Resend inbound webhook and its secret on Railway
- [ ] "Go" to the CR tab: it builds the pieces above, dry-runs, then switches on for that date only
