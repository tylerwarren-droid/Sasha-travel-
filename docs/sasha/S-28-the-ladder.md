# S-28 — The ladder: form, then email, then phone. Specified, not built

**Filed:** 29 September 2026, night. **Report only.** Tomorrow's demo stays **Psi (dry run)** or the
self-hosted venue. Nothing below is reachable by morning (§6).

## 0. The shape, and the one rule that keeps it safe

The act is tried rung by rung, **form → email → phone**, falling down the ladder until one rung *reaches the
venue*.

⛔ **The rule that makes a ladder safe: fall down only on "not available" or "failed before anything reached the
venue". Once any rung may have reached the venue, the automatic descent stops.**
- a form `submitted_unread`, an email accepted by the mail server, or a call that connected: each **may have
  landed**;
- trying the next rung then would be a **second request** to the same venue, which is a double booking, or two
  quotes for one tattoo;
- another rung after that needs **a new intent, a new read-back and a new yes**, exactly as a retry does today
  (contract §9).

**Kept on every rung:**
- the approval bound to a hash of the exact act;
- the payment stop: a deposit request on any rung stops, and needs its own yes;
- the venue's own words, shown to the user;
- an outcome that moves up only on evidence and never down on silence. That is Austen's rule, as in the
  helper.

## 1. Rung 1 — the form (what exists)

| | |
|---|---|
| **available when** | the venue's own page serves a first-party form with the booking fields. **Today that means a venue with a map (Psi).** A live survey is the week, and Gate 1 showed most venues serve no such form (§6) |
| **Sasha says** | the five read-back lines; line 5 by mode |
| **the act** | the helper fills and submits **on the user's device** (contract §1) |
| **what comes back, and how we know** | the page after, read on the device: accepted (with its reference), a known refusal, or **neither → the page's own words, shown to the user** (S-27) |
| **when it fails** | page did not load, form changed, CAPTCHA, `option_not_served`: **nothing reached the venue**, so **fall to rung 2**. `submitted_unread`: it **may have landed**, so **stop the ladder** and show the words |

## 2. Rung 2 — email: for a tattoo studio, the product

⚠ **Email is not a lesser form.** For a tattoo studio the act is *"send my design request"*, and the EU sample
agrees: studios quote and the date is agreed later. Here email **is** the booking channel.

| | |
|---|---|
| **available when** | the venue publishes an address: a `mailto:` or visible address on **its own site**, or its Google Business profile. The source is recorded with the address, and a syntactic check is run (the signer's `email_can_receive_confirmation` already exists). **Deliverability is only known by sending** |
| **Sasha says** | **the email itself, read back**: *"I'll email Getink Tattoo from Sasha, on your behalf: subject 'Tattoo request — fine-line botanical, forearm'; 'Hello, I'm writing for Jon Peters…' — and their reply comes back to me. Shall I?"* **The yes binds to the hash of the exact subject, body and recipient**, the same binding as the form's |
| **the act** | Sasha's server sends **from Sasha's own verified domain**, from and reply-to **`act-{intent}@<inbound domain>`**. ⚠ Not the user's device: an email concierge writes from its own address, and that is honest, since the email says who is writing and for whom |
| **what comes back, and how we know** | **the reply, caught by address**. This is Applied Diligence's proven pattern (P803kd): an inbound webhook, **svix-verified**, receives every mail to `act-{uuid}@…` and matches it **by the address it was sent to**, never by guessing from content. The reply is appended to the act. **The venue's own words are shown to the user**, and the user's reading ("they quoted €300, next Tuesday") is recorded **as theirs**. An LLM summary, if ever added, is **labelled as an AI reading**, never as the venue's answer |
| **when it fails** | a **bounce** (the provider's bounce webhook) means **nothing reached them**, so **fall to rung 3**. **No reply** is **outstanding, never "declined"**: silence is its own state (Pacioli completeness, §4). After a set time the user is told *"no reply yet"*, and a phone call becomes **their** new choice, not an automatic descent |

**What rung 2 needs, none of which exists in Sasha:**
1. **A sending domain** verified in Resend: SPF and DKIM in the founder's DNS (e.g. `mail.kanoe.ai`). Today's
   sender is Resend's **sandbox** address.
2. **An inbound domain**: MX records to Resend inbound, and a webhook secret (`svix`) on Railway. **Sasha
   receives no email today** (S-18).
3. `POST /api/booking/inbound`: verify the svix signature, parse `act-{uuid}` from the To address, and append.
   Unmatched mail is **quarantined**, never guessed onto an act.
4. The email read-back and its hash; the send, **checking Resend's answer** (today's code does not); and the
   bounce webhook.
5. Showing the reply in the conversation, and recording the user's reading.

## 3. Rung 3 — phone

**What really exists:**
- `restaurant_agent.call_restaurant`, which posts to Bland's `/v1/calls` with a free-text task;
- it is **called by nothing**;
- it **does not check the response** (`called: True` even on an error);
- **nothing reads the call's outcome or transcript**;
- and the LLM decides to call with **no read-back and no yes**.

**It is a stub that would report calls it never made, and could make calls nobody approved.**

| | |
|---|---|
| **available when** | a published number (a `tel:` link, its site, Google Business), **and** a calling provider configured, **and** the venue's country allowing an automated call |
| **Sasha says** | **the brief, read back**: who is calling, for whom, what it will ask, and what it will **never** do (give a card, agree to a deposit, book on a different day). A live conversation's exact words cannot be hashed in advance, so **the yes binds to the brief and its limits**, and anything outside them ends the call as *"I'll check with them and call back"* |
| **the act** | an AI voice call **that says it is an AI assistant calling on the guest's behalf** at the start. ⚠ The EU AI Act's transparency duty applies to systems talking to people from August 2026, and **call-recording consent is per country**. Both are a legal read before the first real call, not an engineering detail |
| **what comes back, and how we know** | the provider's end-of-call webhook: status, duration, **the transcript**. The venue's own words are shown to the user; their reading is recorded as theirs. *"Connected"* is not *"booked"* |
| **when it fails** | no answer or voicemail: **nothing agreed**, so it is **outstanding**, and a retry is a new yes. Answered but unresolved: *"they'll call you back"*, **in their words** |

## 4. Pacioli, with three channels

**He never judges and never reads a verdict into silence.** Two of his jobs apply:
- **Completeness is the main one.** Each rung attempt is an **ask**; each rung's events are dated and evidenced:
  form submitted (`started`), page read (`arrived` or not), email accepted by the server, bounce (`failed`),
  reply (`arrived`), call connected, transcript. He answers *"what did we ask for, on which rung, and what came
  back?"*: outstanding, failed, arrived. **The rung is part of the ask**, so "form failed → email arrived" reads
  as one request that moved down the ladder, not two bookings.
- **Reconciliation** where two rungs **both** returned something about the same request (the form's page said
  *"requested"*, and a later email said *"confirmed for 8:30"*). He says where they **agree and differ, field by
  field**, and never which is right.

His output is the audit trail, not evidence (founder decision, 28 September).

## 5. What the page and chat show

**One line per request, with its rung:** *"Getink Tattoo — design request · by email · sent 21:14 · waiting
for their reply."* Then, when it comes: **their words**, and *"Did they say yes?"* for the user to read.

**Never "booked" on silence; never a rung hidden.**

## 6. Honestly reachable, and what is a week

| piece | reachable | why |
|---|---|---|
| **tomorrow's demo** | **Psi dry run** (built, deployed, Stage E green) or the self-hosted venue | the ladder needs everything below |
| **stop `restaurant_agent`'s fake successes** (check Resend's and Bland's answers) | an hour | it is called by nothing today, so there is no urgency; but before it is ever wired, it must stop reporting sends it never made |
| **WhatsApp click-to-chat**, a rung the EU sample says most venues actually use | **hours** | a `wa.me/<number>?text=<the read-back>` link: **the user's own WhatsApp sends it**, the act originates on their device, and the reply goes to **them**. Sasha records *"sent from your WhatsApp; their reply comes to you"*, honestly. No integration, no Meta approval. **The cheapest real rung** |
| **rung 2, email end to end** | **2–4 days**, plus the founder's DNS | a sending domain, an inbound domain and webhook, act addressing, the email read-back, reply display, bounces. The pattern is proven in AD; Sasha has none of it |
| **rung 1 live survey** (any venue with a plain form) | **a week**; Gate 1 showed it reaches few venues | the role vocabulary in hours, the survey and read-back in days; wizards, calendars and platforms stay out |
| **rung 3, phone** | **a week or more**, plus a legal read | approval binding for a brief, AI disclosure, recording consent per country, outcome webhooks, cost per minute |
| **the ladder orchestrator and Pacioli wiring** | 1–2 days after the rungs exist | the descent rule of §0, asks and events per rung, and the one-line status |

**Recommended order after the meeting:**
1. WhatsApp click-to-chat (hours; reaches the venues the sample says are there).
2. Email end to end (days; the tattoo studio's product).
3. The ladder and Pacioli's completeness across rungs.
4. Phone last, after the legal read.
