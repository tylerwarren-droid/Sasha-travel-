# DIVE · the switch-on list for rehearsal day

*CR 66 wrote this list; CR 67 built everything it needs. **Today it is all OFF.** With none of the variables below set,
DIVE behaves exactly as before: messages are captured, never sent, and the test drawer plays the suppliers.
**0 real messages** until you paste the keys.*

Two things become real on rehearsal day:

- **The boat's WhatsApp**, to Jon's phone. In the demo Jon gets 2 messages and sends 2 replies.
- **The gear shop's email**, to an inbox we own.

Each one switches on **only when all of its variables are present**. Half of them means off. It only ever messages an
**allow-listed** number or address: anyone else stays simulated, exactly as today.

**Where you paste every key:** DIVE's variables on Railway (DIVE's own service, never Sasha's):
https://railway.com/project/8d53b07a-eff6-4206-98b1-220a67a2915a/service/bd0252c7-4168-4719-b8d5-09d7e51b6640/variables

There, click **New Variable**, paste the name and the value, and repeat for each one. Then click **Deploy** (Railway
asks you to apply the changes). It takes about 2 minutes. **Never paste a key in chat or in a message to a tab.**

---

## 1 · The real WhatsApp to Jon's phone

### Why Sasha's number can't be used

Sasha's number is +44 7915 914215, "KANOE".

1. **A WhatsApp number has one "a message came in" address.** Sasha's is her own webhook, so Jon's "ΝΑΙ" would land
   in Sasha's venue pipeline, never in DIVE. Changing that means touching Sasha, which the isolation rule forbids.
2. **The boat would see "KANOE" as the sender** of a booking request in Blue Kyma's name.
3. **Twilio's shared test number (+1 415 523 8886) is taken too.** On Sasha's Twilio account it is already wired to
   Sasha's guest service.

So DIVE gets its **own Twilio account**. For rehearsal day: its free WhatsApp Sandbox (option A). For a real pilot:
its own WhatsApp sender (option B, at the end of this section).

### A · Rehearsal day: what you do, in order (about 15 minutes)

1. **Create a separate Twilio account for DIVE** at https://www.twilio.com/try-twilio. You do this; I never create
   accounts.
   - Use an email that is **not** Sasha's.
   - Not a subaccount of Sasha's: DIVE needs its own sandbox and its own webhook.
2. **Open its WhatsApp Sandbox:** https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
   - Note the join phrase it shows ("join " plus two words).
3. **Jon joins from his phone.** He sends that phrase to **+1 415 523 8886** on WhatsApp.
   - The sandbox forgets him after 3 days, so do this within 3 days of the run.
4. **Point the sandbox at DIVE**, on https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox:
   - **When a message comes in:** `https://agapi-dive-demo-production.up.railway.app/hooks/twilio/whatsapp`, method **POST**
   - Click **Save**.
5. **Paste on Railway** (the link at the top). Both keys are on the account's home page, https://console.twilio.com:

   | Name | Value |
   |---|---|
   | `DIVE_TWILIO_ACCOUNT_SID` | the **Account SID** (starts with AC) |
   | `DIVE_TWILIO_AUTH_TOKEN` | the **Auth Token** (click to reveal). It also proves each webhook really comes from Twilio. |
   | `DIVE_WHATSAPP_ALLOW` | Jon's number, international format with no spaces, e.g. `+30690…`. The **only** number DIVE will WhatsApp for real, and the only one whose messages it reads. |
   | `DIVE_REAL_WHATSAPP` | `1`. **The on switch. Paste it last.** Delete it to switch WhatsApp off again; the keys can stay. |

   - Blue Kyma's (fake) website then lists Jon's number for Aegean Boats on its own.
   - (`DIVE_WHATSAPP_FROM` is only for option B. Without it, DIVE sends from the sandbox number.)

### Jon says hi on the morning of the run

- WhatsApp only allows a message **within 24 hours of the person's last message to us**.
- So **on the morning of each run (rehearsal day and demo day), Jon sends "hi"** to +1 415 523 8886.
- **"The day before" is not enough** if the run is more than 24 hours later.
- The start page shows it arrived, and until when the window is open. Without his hi, DIVE refuses to send and shows
  "outside WhatsApp's 24-hour window: ask them to send 'hi' first". That is never shown as a no.

### If Jon writes STOP

- DIVE sends him **nothing more**, real or not.
- The booking is **not** marked as a no. The console says "Aegean Boats sent STOP … Not a no: ask them by phone".
- When he writes **START**, messages are back on.

### B · A real WhatsApp sender, for a pilot (about 1 to 2 days)

1. Do step 1 of A.
2. Buy a number in that account: https://console.twilio.com/us1/develop/phone-numbers/manage/search
3. Create the sender: https://console.twilio.com/us1/develop/sms/senders/whatsapp-senders → **Create new sender** → the
   number → **Continue with Facebook**.
   - Choose **Kanoe's existing business portfolio** (verified for Sasha).
   - Choose a **new** WhatsApp Business Account, so Sasha's quality rating is never shared.
4. Set a display name, e.g. "Kanoe Demo". Meta reviews it, which takes hours, up to 2 days. A fictional "Blue Kyma" is
   likely to be refused.
5. Point the sender's webhook at the same address as A step 4.
6. Paste the same four variables as A, plus `DIVE_WHATSAPP_FROM` = the new number.

---

## 2 · The real gear email

### Why not Sasha's Resend account

- Sasha sends from `booking.kanoe.ai`.
- Resend sends **every** email received on an account to that account's webhooks. In a shared account, the gear
  shop's replies would reach Sasha, and her guests' replies would reach DIVE.
- So DIVE gets its **own Resend account and its own subdomain**.
- DIVE also ignores any mail not addressed to its own domain, and any sender not on its allow-list. It never even reads
  those.

### What you do, in order (about 20 minutes, most of it waiting for DNS)

1. **A separate Resend account for DIVE:** https://resend.com/signup. You do this.
2. **Its domain:** https://resend.com/domains → **Add domain** → `dive.kanoe.ai`.
   - Turn on **receiving** for it.
   - Add the records Resend shows (for sending, plus an **MX** record for receiving) at kanoe.ai's DNS provider. They
     are new records for the new subdomain only. **Nothing about demo.kanoe.ai changes.**
   - Wait for **Verified**.
3. **One key:** https://resend.com/api-keys → **Create API key** → permission **Full access**.
   - DIVE needs it to send the email **and** to read the reply's text: Resend's notification doesn't include the words.
   - The account holds only DIVE, so full access reaches nothing else.
   - (If you'd rather split it: a **Sending access** key as `DIVE_RESEND_API_KEY`, plus a **Full access** key as
     `DIVE_RESEND_READ_KEY`.)
4. **The reply webhook:** https://resend.com/webhooks → **Add endpoint**:
   - URL `https://agapi-dive-demo-production.up.railway.app/hooks/resend/inbound`
   - event **email.received**
   - Then open it and copy its **Signing secret** (starts with whsec_).
5. **The gear inbox:** a mailbox **we own** that you can open on the second screen.
   - A fresh address made for the demo, e.g. a new Gmail you create.
   - Not the founder's own mailbox, and never a real business.
6. **Paste on Railway** (the link at the top):

   | Name | Value |
   |---|---|
   | `DIVE_RESEND_API_KEY` | the key from step 3 |
   | `DIVE_EMAIL_FROM` | `Blue Kyma Diving (demo) <bookings@dive.kanoe.ai>` |
   | `DIVE_EMAIL_ALLOW` | the gear inbox from step 5. The **only** address DIVE emails for real, and the only sender it reads. |
   | `DIVE_RESEND_WEBHOOK_SECRET` | the signing secret from step 4. It proves each email notice really comes from Resend. |

   Blue Kyma's (fake) website then lists the gear inbox for Kyma Gear on its own.

- The gear shop's reply counts **only for what they typed above the quoted request**. Our "Reply YES or NO" below it is
  never read as their answer.
- STOP / START work as on WhatsApp.

---

## 3 · The 2-minute live check (sends nothing)

Do this after pasting the keys and once Railway has redeployed:

1. Open https://agapi-dive-demo-production.up.railway.app/start
   - "Where things stand" says **Boat WhatsApp: REAL · Gear email: REAL**.
   - If either still says "simulated", a variable is missing or misspelled. Compare the names with the tables above.
2. Click **Reset demo**.
3. **Jon sends "hi"** to +1 415 523 8886.
   - Reload /start: **"Jon's WhatsApp: last message … · the 24-hour window is open until …"**.
   - If it still says "nothing received yet", check the sandbox's webhook address (1 · A, step 4).
4. **From the gear inbox, email "hi"** to `bookings@dive.kanoe.ai`.
   - Reload /start: **"Gear inbox: last email received …"**.
   - If not: check the Resend webhook (2, step 4) and that the domain shows Verified with receiving on.
5. Click **Reset demo** again (Jon's window stays open). You're ready: run the demo from step 2 of
   [run-the-demo.md](run-the-demo.md), with Jon and the gear inbox answering for real instead of the test drawer.

So far nothing was sent to anyone. In the run itself:

- Jon gets 2 WhatsApps: the verification and the booking request.
- The gear inbox gets 2 emails: the verification and the request.

To switch WhatsApp off at any moment, delete `DIVE_REAL_WHATSAPP`. To switch the email off, delete `DIVE_EMAIL_ALLOW`.
Then **Deploy**.

---

## What CR 67 built (all on `cr/dive`, in `dive_service/` only)

| Piece | What it does |
|---|---|
| DIVE's own WhatsApp sender | A Twilio call from DIVE's own account, only to `DIVE_WHATSAPP_ALLOW`, only inside the 24-hour window, never after STOP. Anything else goes the simulated way, as before. |
| `/hooks/twilio/whatsapp` | Checks Twilio's signature (a wrong one is refused). Reads only the allow-listed number. Each reply goes through the same classifier as the test drawer, then to the waiting verification or booking leg. A repeated delivery is read once. |
| The real gear email | Unchanged: real only with the key, the from address and an allow-listed address. It now also stops after STOP. |
| `/hooks/resend/inbound` | Checks Resend's signature (a wrong or stale one is refused). Reads only DIVE's domain and the allow-listed sender, and only what they typed above the quote. Matched to the booking by its reference, then through the classifier. |
| The fake site's contacts | Read from the variables: the one allow-listed number and inbox. Otherwise `DIVE_BOAT_WHATSAPP` / `DIVE_GEAR_EMAIL`, otherwise the made-up ones. |
| /start and /health | Show what is real, and when Jon's hi and the gear email arrived. Times and yes/no only, never a number, an address or a key. |
