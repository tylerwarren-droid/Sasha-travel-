# Sasha 210 · the full loop — ten scripted voice conversations (08 Oct 2026 11:02 UTC)

| # | conversation | turns | result | retried | first sound, median ms |
|---|---|---|---|---|---|
| 1 | book it without picking | 4 | ✅ |  | 1501 |
| 2 | picks another flight by voice, then book it | 5 | ✅ |  | 1501 |
| 3 | taps another flight, then book it | 5 | ✅ |  | 1500 |
| 4 | what's the total, then book it | 5 | ✅ |  | 1503 |
| 5 | one thing at a time | 8 | ✅ |  | 1501 |
| 6 | travellers given up front | 3 | ✅ |  | 1501 |
| 7 | not yet, then yes | 5 | ✅ |  | 1501 |
| 8 | is it booked? | 5 | ✅ |  | 1501 |
| 9 | make it three of us | 5 | ✅ |  | 1501 |
| 10 | taps the flight home, total, book it | 6 | ✅ |  | 1501 |

## 1 · book it without picking

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It's a loop from Hanoi down to Saigon, with Hoi An's beaches and a lot of food stops along the way. The Iberia nonstop gets you into Hanoi early on the 22nd. The whole trip for the two of you comes to €2,770.81. The flight home is the pricey part. There's a cheaper direct Iberia back from Saigon on the cards if you'd like it. Just say the word and I'll swap it in.
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Happy to. For the airline I need each traveller's title, full name as on the passport, and date of birth, for you and your travel companion.
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Mm, let me think.
  - *say:* Thanks, Tyler, I've got you and Sam saved. That's five stays from Hanoi down to Saigon. You fly Iberia direct from Madrid on Saturday 21 November, landing in Hanoi early on the 22nd. The way home is Qatar Airways from Saigon on Monday 30 November, with one stop. The total for both of you is €2,770.81. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Bear with me a second.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Nothing is confirmed until it's paid. Once you've paid, I'll check that everything has gone through.
  - tools: book
  - 📱 the payment link reached the phone

## 2 · picks another flight by voice, then book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together: nine days from Hanoi down to the Mekong, with a stay for each night. Hoi An's beaches and Saigon's street food cover the two things you asked for. The Iberia flight leaves Madrid on the 21st and lands in Hanoi early on the 22nd. The whole trip comes to about €2,770.81 for the two of you. The flight home is the pricier one, and there's a direct Iberia option that's cheaper, so have a look at the cards. Want me to swap it?
  - tools: propose_trip
- **Traveller:** Can we have the cheapest flight out instead?
  - *filler:* Let me see.
  - *say:* The cheapest flight out is the Iberia one you already have, leaving Madrid at 8:30 on the 21st and landing in Hanoi at 4:25 on the 22nd. Nothing changes, and the total stays at about €2,770.81. Should I look at the flight home instead, since that's where a cheaper option might be?
  - tools: choose_offer
- **Traveller:** Book it.
  - *filler:* Mm, let me think.
  - *say:* I just need a few details for the airline. For each of you, what's the full name as it appears on your passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Bear with me a second.
  - *say:* Thanks, Tyler, you're both saved. Here's what I'd book: five hotels from Hanoi down to Saigon, the direct Iberia flight out from Madrid on Saturday 21 November, and the Qatar Airways flight home from Saigon on Monday 30 November. It comes to €2,770.81 for the two of you. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes, go ahead.
  - *filler:* Let me have a look.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid. Once you've paid, I'll check the status and confirm.
  - tools: book
  - 📱 the payment link reached the phone

## 3 · taps another flight, then book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Tyler, here's your Vietnam trip. It starts in Hanoi's food streets, then goes down the coast to Hoi An for beach days at the Nam Hai. It finishes in Saigon and the Mekong Delta. The flights and a stay for each night are chosen, and the whole trip comes to €2,770.81 for the two of you. You leave Madrid on the 21st and land in Hanoi early on the 22nd. There's a direct Iberia flight home on the cards that's quicker than the one I picked, so have a look if you'd rather swap. Does this feel right, or should I give it more beach time?
  - tools: propose_trip
- **Traveller:** the British Airways flight out at 08:30
  - *filler:* Let me see.
  - *say:* Swapped. You're now on the British Airways flight out of Madrid at 08:30 on the 21st, landing in Hanoi early on the 22nd. The whole trip now comes to €2,792.57.
  - tools: choose_offer
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* Before I can book, I need each traveller's details for the airline. For you and your companion, could you give me the full name as on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler. I've got you both down. Here's what you'd be booking: five hotels from Hanoi down to Saigon, the British Airways flight from Madrid on Saturday 21 November, and the Qatar Airways flight home from Saigon on Monday 30 November with one stop. The total is €2,792.57. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Mm, let me think.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Once it goes through, the trip is booked, and I'll check the status as soon as you've paid.
  - tools: book
  - 📱 the payment link reached the phone

## 4 · what's the total, then book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* I've put together nine days running from Hanoi down to the Mekong. You'd have Ha Long Bay, Hoi An for the beach and the food, and Saigon for the street eating. The Iberia nonstop leaves Madrid on the 21st and lands in Hanoi at dawn on the 22nd. The whole trip comes to €2,770.81 for the two of you, and the other flights are on the cards if you want to compare. Do you want more beach time in Hoi An, or is this balance right?
  - tools: propose_trip
- **Traveller:** What's the total?
  - *filler:* Let me add it up.
  - *say:* It comes to €2,770.81 for the two of you, with the flights and the stays included.
  - tools: get_total
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* Before I can book, I need each traveller's details for the airline. For you and your companion, could you give me the full name, title and date of birth, as they appear on your passports?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Let me see.
  - *say:* Thanks, Tyler, I've got you both down. That's five hotels across the trip. The flight out is Iberia nonstop from Madrid on Saturday 21 November. The flight home is Qatar Airways with one stop, leaving Saigon on Monday 30 November. The total is €2,770.81 for the two of you. Shall I go ahead and book it?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Sending it to your phone.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until the payment goes through. Once you've paid, I'll check that everything has gone through.
  - tools: book
  - 📱 the payment link reached the phone

## 5 · one thing at a time

- **Traveller:** Hi, I'd love to go to Vietnam.
  - *say:* Vietnam, what a choice! It's a country that rewards slow mornings and long dinners. Is this a trip for you on your own, or who's coming along?
- **Traveller:** Two of us.
  - *say:* Two of you, lovely. And do you have a rough idea of when you'd like to go, and for how long?
- **Traveller:** From 22 November, for 8 nights.
  - *filler:* One moment.
  - *say:* Late November is a good time for it: the south is dry, the crowds are thin, and Hoi An is gorgeous. I've started sketching the trip. Where will you be flying from?
  - tools: prepare_trip
- **Traveller:** Beaches and food.
  - *filler:* Let me see.
  - *say:* Beaches and food is the best way to do Vietnam. Think grilled seafood on the sand in Da Nang and Hoi An, then bowls of noodles in the old town. I'm shaping the trip around that now. Which city will you be flying from?
  - tools: prepare_trip
- **Traveller:** From Madrid.
  - *filler:* Let me put that together.
  - *say:* Here's what I've put together: nine days that run from Hanoi down to the Mekong Delta, with Hoi An's beaches and Saigon's food in the middle. The Iberia nonstop gets you into Hanoi early on the 22nd, and the whole trip comes to about €2,770.81 for the two of you. Have a look at the other flights home. There's a nonstop that might suit you better than the one with a stop. Or if you'd rather spend more time on the beach and less on the move, tell me and I'll rework it.
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* I'll just need a few details for the airline first. For each of you, what's your full name as it appears on your passport, your title, and your date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler and Sam, you're both saved. I have five hotels, from Hanoi through Ha Long Bay, Hue and Hoi An to Saigon. The Iberia nonstop leaves Madrid on Saturday 21 November and lands in Hanoi early on the 22nd. You fly home with Qatar Airways, with one stop, on Monday 30 November. The total comes to €2,770.81 for the two of you. Shall I go ahead and book it?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Mm, let me think.
  - *say:* The payment link is on your phone now, and Apple Pay works there. Nothing is booked until the payment goes through. Once you've paid, I'll check the status and tell you when it's confirmed.
  - tools: book
  - 📱 the payment link reached the phone

## 6 · travellers given up front

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid. The travellers are Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* One moment.
  - *say:* Here's what I've put together for you and Sam: nine days from Hanoi down to the Mekong, with Hoi An as your beach stretch and plenty of street food along the way. It comes to about €2,770.81 all in. You fly out of Madrid with Iberia on the 21st and land in Hanoi early on the 22nd. The way home is a Qatar flight from Saigon on the 30th. There's a direct flight home that costs less, so say the word if you'd like me to swap it in. Does the route feel right, or would you rather spend more time on the coast?
  - tools: propose_trip, save_travellers
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Both your details are saved, Tyler. Here's what I'd book: five hotels from Hanoi down to Saigon, Iberia direct from Madrid on Saturday 21 November, and Qatar Airways home from Saigon on Monday 30 November with one stop. The total is €2,770.81. Shall I go ahead?
  - tools: propose_trip, save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Sending it to your phone.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Nothing is confirmed until the payment goes through, and I'll check the status once you've paid.
  - tools: book
  - 📱 the payment link reached the phone

## 7 · not yet, then yes

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* I've put together a route from Hanoi down to the Mekong Delta, with Hoi An's beaches and plenty of street food along the way. The flight out is Iberia nonstop, leaving Madrid on the 21st and landing in Hanoi early on the 22nd. The flight home is Qatar from Saigon. The whole trip comes to €2,770.81 for the two of you. There are other flights on the cards if you'd like to look. Iberia also flies nonstop home on the 30th for less. Since you're after beaches, would you rather slow it down and spend longer in Hoi An and less time hopping between cities?
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* I just need a few details for the airline. For each of you, what's the full name as on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler, I have you both down. Here's what I'd book. There are five hotels, from Hanoi down to Saigon. The flight out is Iberia nonstop on Saturday 21 November. The flight home is Qatar Airways with one stop on Monday 30 November. The total is €2,770.81 for the two of you. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Hmm, not yet.
  - *say:* No rush, Tyler. Is it the price, the flight home, or the pace of the route that's giving you pause? I can swap in the Iberia nonstop home, or spend less time hopping and more on the beach in Hoi An.
- **Traveller:** OK, go ahead.
  - *filler:* Mm, let me think.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Once it goes through, the trip is yours. I'll check it's confirmed as soon as you've paid.
  - tools: book
  - 📱 the payment link reached the phone

## 8 · is it booked?

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It starts in Hanoi and ends in the Mekong Delta. Food is the thread all the way through. Hoi An gets the beach time, with a beachfront stay at the Nam Hai. I've picked flights that fit, and the whole trip for the two of you comes to about €2,771. The other flight options are on the cards if you'd like to swap. Do you want more beach time, or is this balance right?
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* For the flights I need both travellers' details. For each of you, what's the full name as it appears on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Mm, let me think.
  - *say:* Thanks, Tyler, I've got you both down. Here's what I'd book: five hotels from Hanoi down to Saigon, and the Iberia direct flight out of Madrid on Saturday 21 November. The way home is Qatar Airways from Saigon on Monday 30 November, with one stop. The total is €2,770.81. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Sending it to your phone.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid. Once you've paid, I'll check that everything has gone through.
  - tools: book
  - 📱 the payment link reached the phone
- **Traveller:** Is it booked?
  - *filler:* Bear with me a second.
  - *say:* Not yet, Tyler. All seven items are still waiting on your payment. Once you've paid on your phone, I'll check again and tell you as soon as it's through.
  - tools: get_status

## 9 · make it three of us

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* I've put your Vietnam trip together, Tyler: Hanoi, Ha Long Bay, Hue, Hoi An, Saigon and the Mekong Delta. Hoi An is your beach stretch, and the food gets a chunk of every stop. The flight out is Iberia direct, leaving Madrid on the 21st and landing early on the 22nd. The whole trip comes to about €2,770.81 for the two of you. The flight home is a one-stop Qatar Airways flight, and there's a cheaper direct Iberia home if you'd like it. Want me to swap that in, or is there more beach time you'd like?
  - tools: propose_trip
- **Traveller:** Actually, make it three of us.
  - *filler:* Let me see.
  - *say:* Three it is, Tyler. I've reworked the whole trip for the three of you, with the same Hanoi to Mekong Delta route and beach time in Hoi An. The flight out is still Iberia direct on the 21st, and the flight home is Qatar Airways with one stop. The total is about €3,676.22. The direct Iberia flight home is cheaper, so say the word if you'd like me to swap it in.
  - tools: prepare_trip, propose_trip
- **Traveller:** Book it.
  - *filler:* Mm, let me think.
  - *say:* I just need a few details for the airline. For each of the three of you, what are the full name as on the passport, title, and date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982; and Alex Warren, Mr, born 5 May 1990.
  - *filler:* Bear with me a second.
  - *say:* Thanks, Tyler, I have all three of you saved. Here's what I'd book: five hotels from Hanoi down to Saigon, Iberia direct out of Madrid on Saturday 21 November, and Qatar Airways home from Saigon on Monday 30 November with one stop. The total for the three of you is €3,676.22. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Sending it to your phone.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Nothing is confirmed until the payment goes through, and I'll check it as soon as you've paid.
  - tools: book
  - 📱 the payment link reached the phone

## 10 · taps the flight home, total, book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's your Vietnam trip, Tyler! It runs from Hanoi and Ha Long Bay down through Hue and Hoi An for the beach and food days, then ends in Saigon and the Mekong. The Iberia direct from Madrid lands you in Hanoi early on the 22nd, and the whole thing comes to about €2,770.81 for the two of you. There are other flights on the cards, including a cheaper direct home, if you'd like to swap.
  - tools: propose_trip
- **Traveller:** the Iberia flight home at 08:30
  - *filler:* Let me see.
  - *say:* Swapped. You're now on the Iberia direct home from Saigon on the 30th at 08:30, landing in Madrid early on 1 December. The whole trip comes to €2,456.28 for the two of you.
  - tools: choose_offer
- **Traveller:** What's the total now?
  - *filler:* Let me add it up.
  - *say:* The total is €2,456.28 for the two of you. That covers both flights and the stays.
  - tools: get_total
- **Traveller:** Book it.
  - *filler:* Mm, let me think.
  - *say:* For the flights I'll need each traveller's title, full name as on the passport, and date of birth. Could you start with yours, Tyler, and then your companion's?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* You're set up for five hotels, from the Sofitel Metropole in Hanoi to the Park Hyatt in Saigon. You fly Iberia direct from Madrid on Saturday 21 November at 08:30, landing in Hanoi early on the 22nd. The Iberia direct home leaves Saigon on Monday 30 November at 08:30. The total is €2,456.28 for both of you. Shall I go ahead and book it?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Bear with me a second.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Once it's paid, I'll confirm that everything is booked.
  - tools: book
  - 📱 the payment link reached the phone
