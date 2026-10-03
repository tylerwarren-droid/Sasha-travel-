# Demo v3: the live Vietnam call (Sasha 128)

*3 Oct 2026. Companion to investor-demo-v2.md §v3.*

## 1. Status

| Piece | State |
|---|---|
| **English abroad** (call language) | **Built and pushed (12afa93).** Details in §1.1. |
| **Twilio: dialling +84** | **OFF.** Twilio's geo permission for Vietnam is disabled (read via the API on 3 Oct; Spain is on). Bland dials through our Twilio number (caller ID +44…), so every +84 call fails until it is switched on. **Founder action, §2.** It is an account security setting, so I didn't change it. |
| **Bland: international** | **Unproven.** Nothing in our setup blocks it, but no +84 call has ever been placed. The first real call proves it or shows Bland's refusal in its own words. |
| **Test call** | **Not placed.** See §1.2. |
| **Consent emails** | Drafted below (§3), for the founder to send from his own address. |
| **Rehearsal call** | Planned (§4). |

### 1.1 How English abroad works

- **When it applies:** the venue's country has no reviewed call script. Vietnam is one; there is no Vietnamese script.
- **What Sasha does:** she calls in **English**, the guest's language. The AI disclosure comes first, as always:
  "Hello, this is Sasha, an AI concierge from Kanoe Technologies SL, calling on behalf of the Warren family…"
- **What the read-back says,** before the yes and inside the approval's hash: *"I'll speak English: I have no
  Vietnamese voice, so I'll speak your language — they may not speak English."*
- **Explicit choice:** a guest can also choose any scripted language. For example, `speak: "en"` at a Spanish venue
  gives "I'll speak English, as you asked."
- **Day and time:** worked out in the venue's own day (Asia/Ho_Chi_Minh).
- **Tests:** 3 new tests; 813 offline tests pass.

### 1.2 Why no test call was placed

- **No +84 call can connect yet,** because Twilio's Vietnam permission is off. We own no +84 number either.
- **Our own test line** is the founder's Spanish mobile. A call to it would only re-prove the +34 leg, which has worked
  since S-36, and it would ring his phone for nothing.
- **The proof that matters** is the first call to a venue that has agreed (§4). That call is the test.

## 2. Founder: switch on Vietnam in Twilio (2 minutes)

1. Twilio Console → **Voice → Settings → Geo permissions**.
2. Find **Vietnam (+84)** and tick it. Leave high-risk special numbers **off**.
3. Save.
4. Tell this tab. I re-read the setting through the API and confirm it.

The numbers we would dial are mobiles and landlines in Hoi An and Hanoi (§3). None is a premium or special prefix.
Twilio lists +84 1900 as high-risk; we never dial it.

## 3. Consent emails (English): approve, then send from your own address

**Note:** the brief listed all three venues under Hoi An. Only **Mate** is in Hoi An; **L'essence de Cuisine** and
**MIAs** are in Hanoi (old quarter, Hoàn Kiếm).

The addresses and phones below were read from each venue's own website on 3 Oct.

| Venue | City | Write to | Sasha would call |
|---|---|---|---|
| Mate Restaurant and Coffee | Hoi An | contact@materes.com | +84 349 786 659 |
| L'essence de Cuisine | Hanoi | lessencedecuisine@gmail.com | +84 988 256 226 |
| MIAs restaurant | Hanoi | info@mias.com.vn | +84 966 396 698 |

Mate's site also lists a personal-looking Yahoo address. I left it out: write only to the business address.

### 3.1 The email (one per venue; fill in the brackets)

**Subject:** Permission for a short test booking call from an AI concierge (Kanoe / Sasha)

> Dear [Mate / L'essence de Cuisine / MIAs] team,
>
> I'm Tyler Warren, founder of Kanoe Technologies, a small company in Madrid. We have built Sasha, an AI concierge that
> books restaurants by phone. She always says, in her first sentence, that she is an AI.
>
> We are presenting Sasha to investors next week. We would love to show a real call to a restaurant in Vietnam, and
> we would like it to be yours, but only with your permission:
>
> - Sasha would call you on [+84 … — your number] at about [time] (Vietnam time) on [day] to book a table for two
>   under the name Warren, in English.
> - We would cancel it straight away by email, the same day. It is a test booking: no table is really needed.
> - The call would be heard live by a small audience. It would not be recorded or published.
> - There is no cost to you.
>
> We would also like **one short practice call** on [Monday 5 / Tuesday 6 October] between 18:00 and 20:00 your time,
> cancelled the same way.
>
> Would you agree? A short "yes" in reply to this email is enough. If another time or number suits you better, or if
> English is difficult for the person who answers, please tell us and we will adapt or not call at all.
>
> Thank you very much,
> Tyler Warren — Kanoe Technologies SL, Madrid — +34 608 44 57 15

**Rules:**
- Calls go only to a venue that has replied **yes in writing**. A cold venue is never called.
- The demo-day booking is cancelled by email the same day, and the practice booking right after the practice.

## 4. The rehearsal call

**When:** Monday 5 or Tuesday 6 Oct, **18:00–20:00 in Hoi An or Hanoi = 13:00–15:00 in Madrid**. Vietnam is UTC+7, with
no daylight saving, and Madrid is on CEST (UTC+2): a 5-hour difference. It is the venues' dinner service, so keep it
under a minute.

**Preconditions, in order:**
1. A written yes from at least one venue (§3).
2. Vietnam switched on in Twilio (§2), and confirmed by this tab.
3. Calls switched on for the founder only (they are per account and the founder is always on), and on the server for
   the window (`SASHA_CALLS_ENABLED=1`), then off again.

**The run** (phone, WhatsApp):
1. "dinner for 2 in Hoi An, Vietnam tonight at 19:30" → pick the agreed venue's card. With calls on, its phone is the
   way Sasha books it.
2. The read-back shows the English line and the "I'll speak English…" note → **Yes**.
3. Sasha calls and gives the AI disclosure, the booking, the recap ("Is that correct?") and their answer.
4. You get the result in their words. Then **cancel at once by email**: "cancel tonight's dinner" → Sasha emails them.

**What the rehearsal proves:**
- the Twilio +84 leg, the Bland +84 leg, and English with staff;
- the time it takes;
- whether Bland transcribes their answer.

**If it fails:**
- Bland's or Twilio's refusal is shown word for word.
- The demo then falls back to the email route (§v3.2 of the demo doc).

## 5. Demo-day timing: say it now

At the demo, a live call to Vietnam reaches a venue that is **open** only if the demo is before about **17:00 Madrid**
(22:00 in Vietnam). After that, restaurants there are closing or closed.

The investors' meeting time decides whether the Vietnam call is live or shown from the rehearsal.
