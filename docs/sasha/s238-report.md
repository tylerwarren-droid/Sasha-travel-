# Sasha 238 — report (11 Oct 2026) · 042 applied, EU's invite, WhatsApp photos / memory / voice

## Live
- main **2520848** (code). Railway **37212de0** SUCCESS, DEPLOY GATE: PASS (149/149, $1.06 / 246 calls). Vercel **dpl_6vSEZSsuDYbrqutCJxTNppPQgPgu** READY.
- Units 2000 OK. **S1 fingerprint byte-identical** to 228's baseline. One deploy, pushed only with no deploy running.

## 042: APPLIED (Tyler's explicit OK)
- **Preview:** 1 orphaned s2_acts row; the rule check allowed bodies|bookings|consent|all.
- **Applied** via Supabase as migration `042_account_purge`.
- **Check: 7 cascades to auth.users:** keep_fills, keep_items, keep_keys, s2_acts, s2_memory, s2_wa_contacts and s2_wa_replies (`*_account_fkey`).
  retention_log's rule now also allows `guest_erasure`. Mailbox row 714.

## 0 · EU234 invite: READY
- `tylerwarren+eu234@gmail.com` invited (scratch account 23d65796). The ops route's own steps ran as the server, with the invitation emailed from Sasha's address.
- A sign-in code was requested exactly as /sign-in does: **HTTP 200**. The code is in Tyler's inbox and wasn't used.
- **Found:** an invited address refuses code sign-in ("Signups not allowed") until its invite link has been opened. For this scratch
  address I confirmed it via Supabase admin (`email_confirm`), so the EU walk can use the code. Mailbox row 715.

## The rehearsal
In process, on the production config. Scratch guest 88c32f25 was linked to a fictional number, and **every outgoing message was captured; nothing was sent to any phone**. Only the media download was stood in for, with fictional fixtures:
- a specimen passport with a correct-check-digit MRZ and no real person;
- a fictional statement;
- a fictional damage photo;
- the voice note, which was Sasha's own TTS.

keep_scan's reading, Deepgram, TTS and the agent all ran for real.

## 1 · WhatsApp photos → the same handlers as /s2: DONE
- **Passport:**
  > [photo, "my passport"] → **[BUTTONS]** "Passport ES ••••456 | Expires 2031-05 | Save it to your Keep? It's kept encrypted; the photo isn't kept." [Yes, save it] [No]
  > [Yes, save it] → "Saved to your Keep: Passport ES ••••456. I'll only ever see that mask."
  > "what's in my Keep?" → "You've got one thing in your Keep: your Spanish passport, ending ••••456…"
- **No caption:**
  > [photo] → **[BUTTONS]** "What's this?" [Passport] [Loyalty card] [Something else]
- **Statement:**
  > [photo, "my bank statement"] → "I found three recurring charges … the gym at €39.00 a month, Netflix at €15.99 and Spotify at €10.99. That comes to €65.98 a month."
- **Accident:**
  > "I've had an accident in Lisbon…" → "Is anyone hurt?" → "No" → "done" → "Next, I need some photos. Start with your car from the front. Send it here…"
  > [photo, "the damage"] → saved to the case as its next shot (`front`) → "Got the front. Next, a photo of your car from behind."
- **Found and fixed in the rehearsal:**
  - A photo sent before the photos step was refused, so it now says so plainly.
  - A card shown twice in one turn is now drawn once.
  - Raw step names are no longer shown.

## 2 · Memory + closing: DONE, with one open behaviour
- **Across screens:** the guest asked on **/s2** for "A table for 2 near Gran Vía on Saturday at 9pm". Their first WhatsApp message got:
  > "Welcome back — we were looking at restaurant in Gran Vía, Madrid, Saturday 17 October 21:00. Want to carry on?" + **[LIST]** the same 5 places (`pick:ChIJ…`)

  It's the same `s2_memory`, used by both screens.
- **Closing:** "thanks!" → "OK! Just tap me if you need me — I'm right here." The agent state shows `dormant = True`. The next message woke her (`dormant = False`).
- **Open:** on that welcome-back turn the model said "Oven Mozzarella … is the one you've picked", which wasn't true, and corrected itself two turns later. It's reading the remembered conversation; the fix is how memory is handed to the model, not this wiring.

## 3 · Voice: DONE
> [voice note] → "🎙 I heard: 'What's in my key?'" (Deepgram, from TTS audio) → "Your Keep holds one thing: your Spanish passport…" + **[MEDIA] 🔊** `…/api/agent/voice/note/<token>.mp3`

- A text message gets a text reply only (unit-tested).
- The note route is live: an unknown token → 404 `{"rule":"gone"}`. Notes live in memory for 1 hour.

## Found and fixed: 237's WhatsApp state
`guest_wa_state` saves only its columns, so 237's `photo_for` and `dormant` would have been lost in production. The agent's WhatsApp state (`photo_for`, `dormant`, `last_seen`, a scan awaiting its yes, the accident shots) now rides in `pending` as its own kind (`wa_agent`).

## Not done / notes
- **Tyler's and Jon's numbers:** not messaged, as instructed. Jon's account still has no linked WhatsApp channel, so the flag does nothing for him until he links.
- **Cleanup:** scratch guests 54e6383a and 88c32f25 deleted (200), with 0 rows left in any public/auth table. 042's cascades took their Keep and memory.
