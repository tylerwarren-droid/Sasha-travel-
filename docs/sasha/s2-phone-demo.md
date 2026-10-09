# S2 on the phone: the 2-minute demo script

*Sasha 219. For Tyler, on his own iPhone, in front of a VC: Sasha as a personal concierge.*

## Read this first: on your account, these steps are REAL

You are signed in as the founder. For your account:

| Step | What really happens |
|---|---|
| **Booking dinner** | Sasha contacts the actual restaurant, through its form, email, booking page or a call. Restaurants and spas are never stood in for on your account (Sasha 186/195). |
| **Emailing someone** | It really sends, from Sasha's own address. Real email is on for you and Jon. |
| **The calendar** | Links only. Nothing leaves your phone until you tap one. |

So, before you start:

1. **Pick a restaurant you'd genuinely book**, for a time you'd genuinely go. Otherwise use plan B in step 4 ("Not yet"); the yes is what makes it real.
2. **Use an address you control for "Marta"**, for example your own second address. Whatever you say there is what she sends to.
3. **Check Google Places has quota left.** On 9 Oct at 07:40 CEST, live venue search failed for everyone: Google returned 429, "SearchTextRequest per day", the daily cap. If it's hit again, there are no cards at all.
   - **How to check:** say step 1 below in a quiet moment. Cards should appear.
   - **If they don't:** raise the cap in Google Cloud (APIs & Services → Places API (New) → Quotas). Otherwise the quota resets at 09:00 Madrid time (midnight Pacific).
4. **Apply migration 036** (mailbox, Sasha 219). Without it, "What have you done for me today?" can miss things after a deploy, because the record is kept in memory until then.
5. **Open project.kanoe.ai/next in Safari**, already signed in. Volume up. Text is fine: you don't have to start the video call. The call is better theatre, but typing is quieter in a meeting.

---

## The script (about 2 minutes)

### 0 · Open (5 s)

**Show:** her face and **"Hey there — what can I do for you?"**

**Say to the VC:** "This is Sasha. She's not a travel app. She's a concierge that actually does things, and she can show you what she did."

### 1 · One request, three jobs (15 s)

**Type or say:**
> Book me dinner tomorrow night near Sol, then email the plan to Marta at ‹your second address› and put it in my calendar.

**What appears:** she asks how many and what time, or goes straight to cards if you said them. She says she'll write Marta's email for your approval once the table is confirmed.

**If it misbehaves:**
- **No cards, and "I can't search restaurants right now":** that's the Google daily quota (see before you start). Say *"I'll show you the rest with a booking she already has."* and jump to step 6.

### 2 · Who and when (10 s)

**Type or say:**
> Two of us, at nine.

**What appears:** five photo cards near Sol, with the rating, the area and "Open Sat 21:00". She names two or three.

**Point out:** "Opening hours, not a promise of a table. She never claims availability she hasn't confirmed."

**If it misbehaves:**
- **She names a place you can't see:** scroll the cards. If it isn't there, say *"Show me the cards again."*

### 3 · Pick one (15 s)

**Tap Choose** on a restaurant, or say its name: *"‹Name›, please."*

**What appears:** one line of read-back saying exactly what she'll do: "I'll send their booking form for Saturday at 21:00, two people, under Tyler Warren." Then **"Shall I send it?"**

**Point out:** "Nothing has happened yet. She reads back the exact action, and only my yes, in my own words, in a later turn, sends it."

**If it misbehaves:**
- **She asks which route** ("email them, or book now?"): answer it. That's the venue's own way of taking bookings.
- **"They can't be booked from here":** pick another card.

### 4 · The yes (15 s)

**Type or say:**
> Yes, go ahead.

**What appears:** **✅ Booked** with the venue's reference, *or* "Requested — I'll tell you when they reply" if it went by email. Then the 📅 **Add to your calendar** card (Google / Outlook / Apple / other), and the email to Marta read back on a **"Ready to send · on your yes"** card.

**Point out:**
- "That's a real booking."
- "The calendar is one tap."
- "The email: same rule. She reads it back and waits."

**Plan B, if you don't want a real booking:** say **"Not yet."** She holds it and books nothing. Show that a question isn't a yes: *"Yes — what are the cancellation terms?"* makes her answer and send nothing. Then go to step 6.

**If it misbehaves:**
- **She reads the booking back again instead of booking:** say *"Yes, book it."* once more. A repeat now keeps the same read-back.
- **"That was prepared over 15 minutes ago":** she re-reads it. Say yes again.

### 5 · The email (15 s)

**Type or say:**
> Yes, send it.

**What appears:** the card turns to **Sent** ("From Sasha's own address"). Marta's inbox gets it from Sasha's address (sasha@booking.kanoe.ai), never yours.

**Point out:** "She emails people for me from her own address. Anything that leaves is read back and approved first, and any reply comes back to her."

**If it misbehaves:**
- **"Not sent":** your account isn't on the allow-list for real email. Check that `SASHA_S2_EMAIL_LIVE` isn't `0` on Railway. Say *"It's switched off in this build — it never pretends."*
- **She asks again:** a question doesn't count as a yes. Say exactly *"Yes, send it."*

### 6 · The proof (20 s)

**Type or say:**
> What have you done for me today?

**What appears:** a short list from her own records: the table booked, the dinner added to the calendar, the email to Marta sent. She adds: "the full list, with proof for each, is on the Activity screen."

**Show:** open **project.kanoe.ai/activity**. Each line has its proof: the venue's reference, the email's provider id, the times.

**Say:** "Every action, with its evidence. She can't claim something she didn't do. The record is what she reads from."

**If it misbehaves:**
- **"Nothing yet today" after you booked:** the Activity record was lost on a deploy, because 036 isn't applied. Show `get_status` instead: *"Is my dinner booked?"*

### 7 · Close (5 s)

**Say:** "Tables, emails, the calendar, and whole trips. One concierge, and every act is read back, approved and proven."

*(Don't claim WhatsApp to a new person yet: until Meta approves the first-contact template, she'll say it isn't possible yet.)*

---

## Things that are true and worth saying if asked

- **Safety:**
  - She acts only on your explicit yes, in your own words, in a later turn. A question with "yes" in it is not a yes.
  - The yes is bound to the exact read-back and expires after 15 minutes.
  - Every act can happen only once, even across restarts.
- **Honesty:** if a service is down she says so. She doesn't say "no restaurants". She never names a place that isn't on your screen.
- **Your words in, never secrets:** a password, PIN or card number typed to her is refused before the model sees it.
- **Guests:** a guest account can't contact a real venue or send real email. Those are captured and shown as "Not sent". Today only you and Jon can.

## If something goes badly wrong

- **Stop and say:** "That's why every action needs my yes — nothing happened." It's true: nothing is sent without one.
- **Cancel a real booking you didn't want:** *"Cancel my dinner."* She reads the cancellation back, then *"yes, cancel it"* sends it, through the same route the booking used.
