# S-32 — Both addresses go to the venue; the phone rung as a concierge

**Filed:** 29 September 2026, night. **Report only.** It writes two founder decisions into the design (S-28 ladder,
S-31 walk) and specifies the three open points.

## 0. Blunt answer

- **Both addresses:** this is right, and it closes the forwarding hop. One precondition can undo it.
  - **Sasha's act address may be given to a venue only once the inbound domain exists and is verified live.**
    Sasha receives no email today (S-18, S-28 §2).
  - An act address that catches nothing is the Greece letter again, **with Sasha's name on it**.
  - The signer must refuse to issue a task carrying one until then (§1.4).
- **The phone:** the opening sentence is in §2.1. "No substitute" and "maybe" become outcomes, and neither can
  move a booking to confirmed.
- ⚠ **`restaurant_agent` today does nothing, because nothing calls it. If it were wired, it would:**
  - report calls and emails that never happened;
  - invite substitutions;
  - skip the AI disclosure on the phone;
  - and could dial numbers **the model guessed** (§3).

## 1. Both email addresses go to the venue

### 1.1 Which address goes where

| the venue offers | Sasha's `act-{intent}@<inbound>` | the client's address | the read-back line |
|---|---|---|---|
| **a form with two email fields**, or one email field and a free-text field | the **email field**: the venue's confirmation system sends there, and the reference reaches the itinerary automatically | the second email field; else **one plain sentence in the free-text field**: *"Guest's own email: …"* ✅ **Founder's decision, 29 Sept: yes, where a notes field exists** | *"They'll have my email and yours. I'll send you the confirmation when it arrives, and it'll be in your itinerary."* |
| **a form with one email field and nothing else** | the email field. **The itinerary is the product** | **not sent** | *"Their form takes one email address, so it'll be mine. I'll send you the confirmation when it arrives, and it'll be in your itinerary."* |
| **email (rung 2)** | From and Reply-To | **CC**: the venue's "reply all" reaches both, and the client holds the thread | the first line, and the email itself is read back (S-28 §2) |
| **phone (rung 3)** | the email she gives if asked | **not given**: the founder said contact details are hers | see §2 |

**Why the lines are part of the approval:**
- The client's address going to a third party is a **disclosure**.
- The line sits **inside the read-back, whose hash the yes binds to**, so the client heard it before saying yes.
- A task whose fields carry the client's address without that line is refused: `address_disclosed_unread`.

⚠ **The one-field case keeps a small hop.** The client's copy comes from Sasha, not the venue. That is a
forward, but an **automatic one, matched by address** (§1.3), not a person remembering to pass a letter on. The
line says it out loud, which is the founder's condition.

### 1.2 Where a confirmation lands

- It lands at `act-{intent}@…` and is matched **by the address it was sent to**, never by guessing from content.
  That is AD's P803kd pattern, svix-verified.
- It is appended to the act. **The venue's own words** are kept; the reference is extracted only where a
  `reference_pattern` is known.
- Otherwise it is **shown to the client**, and **their** reading is recorded as theirs.
- **The forward to the client is sent at once, and Resend's answer is checked.** A failed forward is itself an
  outcome: *"I have their confirmation but could not send it on to you"*. It is never silent.
- **Mail that matches no act is quarantined, never attached by guesswork.**

### 1.3 What it changes in code

1. **The signer's live email check** (`issue.py` step 3). Today it checks that `confirmation_email_field` can
   receive mail. It changes to:
   - the email field holds **exactly the act address for this intent**, on the **verified inbound domain**;
   - the client's address, where sent, passes `email_can_receive_confirmation`.
2. **`venues.py` / the mapper**: the field assignment above, from the S-29 roles. Where a form has two email
   fields, the **first by page order** takes Sasha's; this is read back.
3. **The read-back builder**: the new line, in one of its two forms.

### 1.4 ⛔ The precondition, as a refusal

`act_address_unroutable`: the signer refuses a live task carrying an act address **unless all of these hold**:
- the inbound domain's MX records point at the receiver (checked live, as the email check checks DNS);
- the webhook secret is set;
- **a test mail to that domain was received within the last 24 hours** (a heartbeat act).

**Until rung 2 is built** (2–4 days plus the founder's DNS, S-28 §6), live tasks keep today's behaviour: **the
client's own address in the one email field.** The read-back then says so honestly: *"They'll send the
confirmation to you."*

## 2. The phone rung, as a concierge

**Standing rules:**
- She calls **on behalf of a named party, never as the client**: *"the Johnson family"*.
- The **name** is read back and approved like every other line. Where the client prefers, it is only a surname
  or *"a guest"*.
- **Contact details are Sasha's**:
  - her act email;
  - **a callback number that is answered**, the provider's inbound number with voicemail transcribed to the act.
- ⛔ **No callback number is ever given that nobody answers.** Until inbound calls exist, the phone rung is
  **unavailable**.

### 2.1 The opening sentence

> **"Hello — my name is Sasha. I'm an AI assistant, an automated voice rather than a person, calling on behalf of
> the Johnson family to book a table. Do you have a moment?"**

**If the call is recorded**, the next sentence, before any booking detail:

> **"This call is recorded so the family has an exact record of what we agree. Is that all right?"**

**Rules around it:**
- **The disclosure is the first thing said, every call, in the venue's language.**
- It is **never** delayed to "sound natural", and never answered with "I'm a concierge" if asked. *"Are you a
  real person?"* gets **"No, I'm an AI assistant."**
- **The recording question is asked where the country requires consent.**
  - If the venue says no: **no recording, and no transcript kept.** She says *"No problem — I'll have the family
    contact you directly,"* and ends the call.
  - The outcome is `recording_declined`, nothing booked.
  - ⚠ **Reason:** without the venue's own words there is no evidence, and an outcome without evidence is not
    recorded as one.
- ⚠ **This is a legal read before the first real call, not an engineering choice.**
  - The EU AI Act transparency duty for systems that talk to people applies from August 2026.
  - Call-recording consent is set **per country, and in the US per state**.
  - The sentences above are the **safe default**: disclose always, ask always.

### 2.2 She never agrees to a substitute

**The brief is what the yes is bound to** (S-28 §3): who, what, when, for how many, and **what she will never
do**:
- agree to a different day, time or party size;
- give a card;
- agree to a deposit;
- accept a hold on the family's behalf.

**When the venue offers another time:**

> *"Thank you — I can't agree to a different time myself. May I note 9:15 and check with the family? I'll call
> back or email."*

- **Outcome `offered_alternative`**, with the offered slot **and the venue's own words** (a transcript excerpt).
- **Brought back to the client:** *"They're full at eight. They offered 9:15 — their words: '…'. Want me to take
  it?"*
- Taking it is **a new read-back, a new yes and a new call or email.**
- **This is the same rule as the wizard's `option_not_served`:** never the nearest one.

### 2.3 The outcomes, and a maybe is its own

| outcome | when | carries |
|---|---|---|
| `confirmed` | the venue said yes **and** her **closing read-back to the venue** was affirmed: *"So that's four, Thursday at eight, under Johnson — is that confirmed?"* | their words; a name or reference if given |
| `declined` | a clear no, with no alternative | their words |
| `offered_alternative` | §2.2 | the slot, and their words |
| **`venue_said`**, the maybe | *"call back tomorrow"*, *"the manager will call you"*, *"we'll see"*, anything neither yes nor no | **their words, shown to the client**. The phone version of the page-after's "neither" (S-27 `page_says`). **Never read as yes or no**; the client's reading is recorded as theirs |
| `no_answer` | no pickup, busy, **or voicemail**. ⚠ **v1 leaves no voicemail**: a message is itself a request that **may have landed**, which stops the ladder (S-28 §0). Hanging up keeps it "nothing reached them" | the provider's status |
| `recording_declined` | §2.1 | — |
| `call_failed` | the provider refused or errored, **checked from its answer** | the provider's own words |

**How an outcome is read:**
- The transcript is **the evidence**.
- A model's classification of it is **labelled as an AI reading**, and **can only propose** `confirmed`,
  `declined` or `offered_alternative`.
- **Where it is unsure, the outcome is `venue_said`.** The status moves up only on evidence and never down on
  silence.

## 3. ⚠ What `restaurant_agent` would do today

**File:** `backend/app/services/restaurant_agent.py`. **Callers: none.** `git grep` finds only docs, and the
conductor never imports it. **So today: nothing.**

**If it were wired:**

| line | what happens |
|---|---|
| **185** `call_restaurant` | posts to Bland and **never checks the status**. On an error reply that is still JSON (a bad key, a malformed number), it returns **`called: True`, `call_id: None`, "*X* being called now."** It **reports a call that never happened.** Only a non-JSON reply raises and returns `called: False` |
| after the call | **nothing reads the outcome**: no webhook, no status poll, no transcript. **Even a real call's result is never known** |
| **175** the task text | *"You are a travel concierge…"*: **no AI disclosure.** *"If that time is not available ask for the nearest available slot"*: **it invites the substitution** §2.2 forbids. `record: True` with **no consent question**. English only |
| **150–160** `send_reservation_email` | **neither Resend answer is checked**; both posts, then `sent: True`. It sends **from `onboarding@resend.dev`**, Resend's sandbox sender, which by Resend's own rule delivers only to the account owner's address, **so a restaurant never receives it, and it still reports sent** |
| **157** | when `SASHA_NOTIFY_EMAIL` is unset, the recipient list contains `""`, and the guest's copy can fail too, **unchecked** |
| **133–142** | tells the guest *"We have sent a reservation request"* and *"They will confirm directly to you"*, **even when the first send failed** |
| **75** `find_restaurant` | asks a model for *"phone (or best guess), email (or best guess)"*. **The call and the email can go to a guessed number or address: a stranger.** ⛔ The worst line in the file |
| **190** system prompt | *"Send reservation email **and** call restaurant simultaneously"*: **two requests to one venue**, the double booking the ladder's descent rule forbids |
| the whole loop | the model decides to call or email **with no read-back and no yes** |

**Recommendation:**
- **Do not wire it.** Replace it, rung by rung, with the S-28 design and this one.
- **Minimum if it is ever touched before then:**
  - check both providers' answers;
  - delete the "best guess" contact line;
  - remove the "nearest slot" instruction;
  - remove "simultaneously".

  About an hour. **It is dead code, so none of this is urgent, and all of it is required before a single real
  call.**
