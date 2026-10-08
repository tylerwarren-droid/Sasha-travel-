# Sasha 210 · the full loop — ten scripted voice conversations (08 Oct 2026 10:47 UTC)

| # | conversation | turns | result | retried | first sound, median ms |
|---|---|---|---|---|---|
| 1 | book it without picking | 4 | ✅ |  | 1501 |
| 2 | picks another flight by voice, then book it | 5 | ✅ |  | 1501 |
| 3 | taps another flight, then book it | 5 | ✅ |  | 1501 |
| 4 | what's the total, then book it | 5 | ✅ |  | 1501 |
| 5 | one thing at a time | 8 | ✅ |  | 1501 |
| 6 | travellers given up front | 3 | ✅ |  | 1500 |
| 7 | not yet, then yes | 5 | ✅ |  | 1501 |
| 8 | is it booked? | 5 | ✅ |  | 1501 |
| 9 | make it three of us | 5 | ✅ |  | 1504 |
| 10 | taps the flight home, total, book it | 6 | ✅ |  | 1501 |

## 1 · book it without picking

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* I've put together a trip that runs from Hanoi down to the Mekong, with Hoi An's beach days in the middle and a lot of eating along the way. With the Iberia direct flight out on the 21st, landing early on the 22nd, and Qatar home from Saigon, it comes to €2,770.81 for the two of you. It covers six stops in nine days, which is a lot of moving around. If you'd rather have more beach time and less packing, I can trim it to Hoi An and Saigon. There's also a cheaper direct flight home on the cards if you'd like it.
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* Happy to, Tyler. The airline needs each traveller's details first. For you and your travel companion, I need the full name as on the passport, the title (Mr, Ms, Mrs, Miss or Dr) and the date of birth.
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler, I've got you both down. That's five hotels, from the Sofitel Metropole in Hanoi to the Park Hyatt in Saigon. You fly out with Iberia direct on Saturday 21 November and come home with Qatar Airways from Saigon on Monday 30 November, with one stop. The total is €2,770.81 for the two of you. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Let me see.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid, so once you've paid I'll check and tell you when everything's confirmed.
  - tools: book
  - 📱 the payment link reached the phone

## 2 · picks another flight by voice, then book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It runs from Hanoi down through Ha Long Bay, Hue and Hoi An, then on to Saigon and the Mekong Delta. The Hoi An days at the Nam Hai are your beach time, and there's plenty of street food along the way. The Iberia direct flight gets you into Hanoi early on the 22nd. You fly home from Saigon with Qatar, and the whole trip comes to €2,770.81 for the two of you. There are other flights on the cards if you'd like to look. Do you want more beach time and less travelling around?
  - tools: propose_trip
- **Traveller:** Can we have the cheapest flight out instead?
  - *filler:* Let me swap that in.
  - *say:* That Iberia flight, leaving Madrid at 08:30 on the 21st, was already the cheapest way out. Nothing changes, and the total stays at €2,770.81. Want me to look at a cheaper flight home, or at a different hotel?
  - tools: choose_offer
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* I just need the details for both of you for the airline. For each person, what's the full name as on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, both of you are saved. The trip has five hotels, from the Sofitel Metropole in Hanoi to the Park Hyatt in Saigon. You fly out with Iberia, direct from Madrid on Saturday 21 November. You fly home with Qatar Airways from Saigon on Monday 30 November. The total is €2,770.81. Shall I go ahead and book it?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes, go ahead.
  - *filler:* Sending it to your phone.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Once it's paid, the trip is booked, and I'll check that it's gone through when you tell me you've paid.
  - tools: book
  - 📱 the payment link reached the phone

## 3 · taps another flight, then book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler! It's nine days running Hanoi, Ha Long Bay, Hue, Hoi An, Saigon and the Mekong Delta. The Hoi An stay and the street food in Hanoi and Saigon should cover your beaches-and-food brief. The flights are Iberia direct out, landing in Hanoi early on the 22nd, and Qatar home from Saigon. For the two of you it comes to €2,770.81 all in. Have a look at the other flights on the cards. The Iberia direct home on the 30th looks like a cheaper way back. Do you want me to swap that in, or would you rather keep the beaches front and centre and spend less time on the road?
  - tools: propose_trip
- **Traveller:** the British Airways flight out at 08:30
  - *filler:* Let me swap that in.
  - *say:* The British Airways flight is in. It leaves Madrid at 08:30 on the 21st and lands in Hanoi at 4:25 on the morning of the 22nd. The new total is €2,792.57. Do you want me to swap in the cheaper Iberia flight home as well?
  - tools: choose_offer
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* For the airline, I need each traveller's full name as on the passport, their title, and their date of birth. Could you give me those for you and your travel companion, Tyler?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler, I've got you and Sam down. Here's what you'd be booking. Five hotels, from the Sofitel Metropole in Hanoi to the Park Hyatt in Saigon. British Airways out on Saturday the 21st. Qatar Airways home from Saigon on Monday the 30th. The total is €2,792.57. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Mm, let me think.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid. Once you've paid, I'll check that everything went through.
  - tools: book
  - 📱 the payment link reached the phone

## 4 · what's the total, then book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together for you both. It runs from Hanoi down to the Mekong, with Hoi An as the beach stop, and it comes to about €2,770.81 all in. Iberia flies you direct to Hanoi, and you fly home from Saigon. It's a lot of moving around for 8 nights. If you'd like more sand and less transit, I could drop a stop or two and give Hoi An more time. Do you want that, or does this feel right?
  - tools: propose_trip
- **Traveller:** What's the total?
  - *filler:* Let me see.
  - *say:* The total is €2,770.81 for both of you. That covers the flights and the stays. Do you want me to keep the route as it is, or trim it so Hoi An gets more beach time?
  - tools: get_total
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* I just need the details the airline asks for. For each of you, what's your full name as it appears on the passport, your title, and your date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Mm, let me think.
  - *say:* Thanks, Tyler, you're both saved. That's five stays: Hanoi, Ha Long Bay, Hue, Hoi An and Saigon. Iberia flies you out of Madrid on Saturday 21 November, and Qatar Airways brings you home from Saigon on Monday 30 November with one stop. The total is €2,770.81. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Bear with me a second.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing's confirmed until it goes through. Once you've paid, I'll check that everything shows as booked.
  - tools: book
  - 📱 the payment link reached the phone

## 5 · one thing at a time

- **Traveller:** Hi, I'd love to go to Vietnam.
  - *say:* Vietnam, what a choice! It's a country that rewards slow mornings and street-side breakfasts. Who's coming along with you?
- **Traveller:** Two of us.
  - *say:* Two of you, lovely. Is this a romantic escape, a friends' trip, or something else? And when are you thinking of going?
- **Traveller:** From 22 November, for 8 nights.
  - *filler:* One moment.
  - *say:* Late November is a good call: the south is dry and the crowds are still thin. I've started shaping the trip. Where will you be flying from?
  - tools: prepare_trip
- **Traveller:** Beaches and food.
  - *filler:* Let me see.
  - *say:* Beaches and food is an easy brief for Vietnam. Think grilled seafood on the sand in Da Nang, Hoi An's street food, and a few slow beach days. Where will you be flying from?
  - tools: prepare_trip
- **Traveller:** From Madrid.
  - *filler:* Let me put that together.
  - *say:* Here's what I've put together: nine days running from Hanoi down to Saigon, with a direct Iberia flight out of Madrid and a Qatar Airways flight home. It comes to €2,770.81 all in. It's a lot of ground for eight nights, though, and you asked for beaches and food. I could keep it to Da Nang and Hoi An for the sand and the street food, with fewer hops between cities. Would you like that, or do you like the grand tour?
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* Happy to. The airline needs a few details for each of you first. For both travellers, could you give me the full name as on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* One moment while I check it all.
  - *say:* Thanks, both of you are saved. Here's what I'd book: five hotels from Hanoi down to Saigon, the Iberia direct flight out of Madrid on Saturday 21 November, and Qatar Airways home from Saigon on Monday 30 November. The total is €2,770.81. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Sending it to your phone.
  - *say:* The payment link is on your phone now, and Apple Pay works there. Nothing is confirmed until it's paid. Once you've paid, I'll check that everything shows as booked.
  - tools: book
  - 📱 the payment link reached the phone

## 6 · travellers given up front

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid. The travellers are Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It's a Vietnam loop from Hanoi down to Saigon, with a beach stay at Hoi An's Nam Hai and plenty of food stops along the way. The flights are Iberia direct out, leaving Madrid on the 21st and landing in Hanoi early on the 22nd, and Qatar home from Saigon. It comes to €2,770.81 all in. It's a lot of ground for 8 nights, so I can slow it down and spend more days on the coast if you'd like. Do you want that, or shall I leave it as it is?
  - tools: propose_trip, save_travellers
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Here's where we are, Tyler. It's five hotels across the trip, from Hanoi down to Saigon. Iberia flies you out of Madrid on Saturday 21 November, and Qatar Airways brings you home from Saigon on Monday 30 November, with one stop. The total is €2,770.81. Shall I go ahead and book it?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Mm, let me think.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid. Once you've paid, I'll check that everything has gone through.
  - tools: book
  - 📱 the payment link reached the phone

## 7 · not yet, then yes

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It's a nine-day run from Hanoi and Ha Long Bay down through Hue and Hoi An to Saigon and the Mekong, with plenty of beach time and street food along the way. The flights are an Iberia nonstop out, landing in Hanoi early on the 22nd, and Qatar home from Saigon, for about €2,770.81 all in. There's a cheaper, faster way home too: a direct Iberia flight from Saigon on the 30th. Want me to swap it in?
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* I just need the airline details for you both. What are the full names, titles and dates of birth for you and your companion?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler. Here's the booking as it stands: five hotels across the trip, and Iberia nonstop from Madrid on Saturday 21 November, landing in Hanoi early on the 22nd. The way home is Qatar Airways from Saigon on Monday 30 November, with one stop. The total for you both is €2,770.81. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Hmm, not yet.
  - *filler:* Mm, let me think.
  - *say:* No problem, Tyler, take your time. Is it the price, the flights, or something about the hotels that's giving you pause? I can swap in the direct Iberia flight home or change a stay if that would help.
- **Traveller:** OK, go ahead.
  - *filler:* Bear with me a second.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Once you've paid, I'll check that everything's confirmed.
  - tools: book
  - 📱 the payment link reached the phone

## 8 · is it booked?

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It's a Vietnam loop from Hanoi down to Saigon, with Hoi An as the beach stop and food all the way. The total is about €2,770.81 for the two of you, with an Iberia nonstop out and Qatar home. You'd leave Madrid on the 21st and land in Hanoi early on the 22nd. There's also a cheaper nonstop home with Iberia on the 30th, if you'd rather take that. Want me to swap it in?
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* I just need the details the airline asks for. For each of you, what's the full name as on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Mm, let me think.
  - *say:* Thanks, Tyler, that's everything I need. Here's what I'd book for you and Sam: five hotels from Hanoi through to Saigon, and the Iberia nonstop from Madrid on Saturday 21 November. The way home is Qatar Airways from Saigon on Monday 30 November, with one stop. The total is €2,770.81. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Bear with me a second.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there.
  - *replace:* Tell me once you've paid, and I'll check where it stands.
  - tools: book
  - 📱 the payment link reached the phone
  - guard: claim: it says booked/paid/confirmed but Pacioli has nothing booked; rewritten
- **Traveller:** Is it booked?
  - *filler:* Let me check.
  - *say:* Not yet, Tyler. Everything's waiting on the payment, so nothing is booked until it goes through. The link is on your phone. Once you've paid, tell me and I'll check again.
  - tools: get_status

## 9 · make it three of us

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* Let me put that together.
  - *say:* Here's what I've put together, Tyler: nine days running Hanoi, Ha Long Bay, Hue and Hoi An, then Saigon and the Mekong Delta, for about €2,770.81 all in. Hoi An is your beach stop, with the Four Seasons Nam Hai right on the sand, and food is the thread through every stop. You fly Iberia direct out, landing in Hanoi early on the 22nd. The flight home is with Qatar, and there's a cheaper direct Iberia option on the cards if you'd like to swap it.
  - tools: propose_trip
- **Traveller:** Actually, make it three of us.
  - *filler:* One moment.
  - *say:* Done, Tyler, it's now set for three. The trip comes to about €3,676.22 all in. It's the same route and the same stays, from Hanoi down to the Mekong Delta, with Hoi An and the Nam Hai as your beach stop. The flights are also the same. Iberia goes direct out of Madrid on the 21st and lands in Hanoi early on the 22nd. Qatar brings you home from Saigon on the 30th. Iberia has a direct flight home that same morning and it's cheaper, so say the word if you'd like me to swap it in.
  - tools: prepare_trip, propose_trip
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* I just need the details the airline asks for, one set per traveller. For each of the three of you, what's the full name as on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982; and Alex Warren, Mr, born 5 May 1990.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler, I have all three of you down. The booking is five hotels: Hanoi, Ha Long Bay, Hue, Hoi An and Saigon. You fly Iberia direct from Madrid on Saturday 21 November. You come home with Qatar Airways from Saigon on Monday 30 November, with one stop. The total is €3,676.22, and you pay in one go on your phone. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Let me see.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until you've paid, so finish that and I'll check it has gone through.
  - tools: book
  - 📱 the payment link reached the phone

## 10 · taps the flight home, total, book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler: nine days running from Hanoi down to the Mekong Delta, for about €2,770.81 all in for the two of you. You fly Iberia direct from Madrid on the 21st and land in Hanoi early on the 22nd. The way home is with Qatar, and there's a cheaper direct Iberia flight back among the cards if you'd like it. It covers a lot of ground, though, and you asked for beaches. Hoi An is the real beach stop. If you'd rather slow down, I could trim it to the central coast and Saigon for food, with more sand and fewer transfers. Want me to do that?
  - tools: propose_trip
- **Traveller:** the Iberia flight home at 08:30
  - *filler:* Let me swap that in.
  - *say:* The Iberia flight home is in. It leaves Saigon at 08:30 on the 30th and gets into Madrid early on 1 December. The new total is €2,456.28. Do you want me to trim the route toward the beaches, or keep it as it is?
  - tools: choose_offer
- **Traveller:** What's the total now?
  - *filler:* Let me add it up.
  - *say:* It comes to €2,456.28 for the two of you, with both flights and the stays included. Shall I trim the route toward the beaches, or keep it as it is?
  - tools: get_total
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* I need a few details for the airline first. For each of you, what's your full name as it appears on your passport, your title, and your date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler, that's you and Sam saved. This is the full booking. It has five hotels: two nights in Hanoi, one on Ha Long Bay, one in Hue, two in Hoi An and two in Saigon. The flights are Iberia direct from Madrid on Saturday 21 November and Iberia direct home from Saigon on Monday 30 November. The total is €2,456.28. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Sending it to your phone.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is confirmed until the payment goes through. Once you've paid, I'll check that everything shows as booked.
  - tools: book
  - 📱 the payment link reached the phone
