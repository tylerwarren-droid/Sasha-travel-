# Sasha 210 · the full loop — ten scripted voice conversations (08 Oct 2026 11:29 UTC)

| # | conversation | turns | result | retried | first sound, median ms |
|---|---|---|---|---|---|
| 1 | book it without picking | 4 | ✅ |  | 1501 |
| 2 | picks another flight by voice, then book it | 5 | ✅ |  | 1501 |
| 3 | taps another flight, then book it | 5 | ✅ |  | 1501 |
| 4 | what's the total, then book it | 5 | ✅ |  | 1501 |
| 5 | one thing at a time | 8 | ✅ |  | 1500 |
| 6 | travellers given up front | 3 | ✅ |  | 1501 |
| 7 | not yet, then yes | 5 | ✅ |  | 1501 |
| 8 | is it booked? | 5 | ✅ |  | 1501 |
| 9 | make it three of us | 5 | ✅ |  | 1501 |
| 10 | taps the flight home, total, book it | 6 | ✅ |  | 1501 |
| 11 | Ecuador, the full loop | 4 | ✅ |  | 1501 |
| 12 | Japan, the full loop | 4 | ✅ |  | 1502 |
| 13 | Morocco, the full loop | 4 | ✅ |  | 1501 |
| 14 | Portugal, the full loop | 4 | ✅ |  | 1501 |
| 15 | Vietnam, the full loop | 4 | ✅ |  | 1501 |

## 1 · book it without picking

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It runs from Hanoi down to Hoi An for the beach, then Saigon and the Mekong Delta for the food. You fly Iberia direct from Madrid on the 21st and land in Hanoi early on the 22nd. The flight home is with Qatar, and the whole trip for the two of you comes to about €2,770.81. There are other flights on the cards if you'd like to compare. The cheapest way home is a direct flight that leaves earlier in the day.
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Before I can book, I need each traveller's details for the airline. Could you give me both your full names as they appear on your passports, your titles, and your dates of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Mm, let me think.
  - *say:* Thanks, Tyler, I've got you both down. That's five hotels, from Hanoi through Ha Long Bay, Hue and Hoi An to Saigon. The flight out is Iberia on Saturday 21 November, and the flight home is Qatar Airways on Monday 30 November. The total is €2,770.81. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Bear with me a second.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is confirmed until the payment goes through. Once you've paid, I'll check the status and tell you when everything is booked.
  - tools: book
  - 📱 the payment link reached the phone

## 2 · picks another flight by voice, then book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It's a trip down the country from Hanoi and Ha Long Bay through Hoi An's beaches and on to Saigon and the Mekong, with plenty of food along the way. It comes to about €2,770.81 for the two of you. The Iberia flight out leaves Madrid on the 21st and lands in Hanoi early on the 22nd. There are other flights home on the cards if you'd like something different. Does the route feel right, or should I lean harder into beach time?
  - tools: propose_trip
- **Traveller:** Can we have the cheapest flight out instead?
  - *filler:* Let me swap that in.
  - *say:* The flight I'd already picked is the cheapest one out. It's the Iberia direct from Madrid at 08:30 on the 21st, and it lands in Hanoi at 04:25 on the 22nd. Nothing changes, so the total is still about €2,770.81. Would you like me to look at a different departure time, or are you happy with this one?
  - tools: choose_offer
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Before I can book, I need each traveller's details for the airline. Could you give me both of your full names as they appear on your passports, your titles, and your dates of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Mm, let me think.
  - *say:* Thanks, Tyler, I've got both of you down. It's five hotels from Hanoi down to Saigon. You fly Iberia direct out of Madrid on Saturday 21 November. You come home with Qatar Airways, with one stop, on Monday 30 November. The whole trip is €2,770.81 for the two of you. Shall I go ahead and book it?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes, go ahead.
  - *filler:* Bear with me a second.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid. One thing I should have said earlier: the hotel prices are estimates, while the flights are quoted. Once you've paid, I'll check that everything shows as booked.
  - tools: book
  - 📱 the payment link reached the phone

## 3 · taps another flight, then book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* I've put your trip together, Tyler. It's Hanoi, Ha Long Bay, Hue, Hoi An, Saigon and the Mekong Delta, with the beach days at Hoi An and plenty of food stops along the way. You fly Iberia direct out of Madrid on the 21st and land in Hanoi early on the 22nd. The way home is with Qatar from Saigon. All in for the two of you it comes to €2,770.81. There are other flights on the cards if you'd like to look, and I can also tilt the route towards more beach time if you want.
  - tools: propose_trip
- **Traveller:** the British Airways flight out at 08:30
  - *filler:* Let me see.
  - *say:* The British Airways flight is in. It leaves Madrid at 08:30 on the 21st and lands in Hanoi at 04:25 on the 22nd. Your new total is €2,792.57.
  - tools: choose_offer
- **Traveller:** Book it.
  - *filler:* Mm, let me think.
  - *say:* I just need the details the airline asks for. For each of you, what's the full name as on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Bear with me a second.
  - *say:* Thanks, Tyler, I've got you both down. It's five hotels from Hanoi through to Saigon, with British Airways out of Madrid on Saturday 21 November. The way home is Qatar Airways from Saigon on Monday 30 November. The total comes to €2,792.57. Shall I go ahead and book it?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Let me have a look.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. The total is €2,792.57. Nothing is booked until you pay, and I'll check as soon as it goes through.
  - tools: book
  - 📱 the payment link reached the phone

## 4 · what's the total, then book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Tyler, I've put together nine days running Hanoi, Ha Long Bay, Hue, Hoi An, Saigon and the Mekong Delta. Hoi An is the beach and food stretch, with the Nam Hai on the sand and a hands-on food day. The total for two is about €2,770.81 with flights. You fly direct with Iberia, leaving Madrid on the 21st and landing in Hanoi early on the 22nd. There's also a direct Iberia flight home from Saigon among the other options, if you'd rather skip the Qatar stopover. Would you like me to swap anything?
  - tools: propose_trip
- **Traveller:** What's the total?
  - *filler:* Let me see.
  - *say:* The total is €2,770.81 for the two of you. That covers the flights and the stays. Some of the hotel prices are estimates, and the flights are quoted. Do you want me to swap anything, or shall I go ahead and book?
  - tools: get_total
- **Traveller:** Book it.
  - *filler:* Mm, let me think.
  - *say:* I just need a few details for the airline. For each of you, what's your full name as it appears on your passport, your title, and your date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Bear with me a second.
  - *say:* Thanks, Tyler, I have you both down. Here's what I'd book: five hotels from Hanoi to Saigon, then Iberia direct from Madrid on Saturday 21 November. The way home is Qatar Airways from Saigon on Monday 30 November, with one stop. The total is €2,770.81. The flights are quoted, but the hotel prices are estimates. Shall I go ahead and book?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Let me have a look.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Nothing is booked until it's paid, so tap through when you're ready.
  - *replace:* Just tell me once you've tapped through, and I'll check where everything stands.
  - tools: book
  - 📱 the payment link reached the phone
  - guard: claim: it says booked/paid/confirmed but Pacioli has nothing booked; rewritten

## 5 · one thing at a time

- **Traveller:** Hi, I'd love to go to Vietnam.
  - *say:* Vietnam, what a choice! It's one of my favourite countries to talk about. Who's coming along with you?
- **Traveller:** Two of us.
  - *say:* Two of you, lovely. Is this a special occasion, or just a well-earned escape? And when were you thinking of going?
- **Traveller:** From 22 November, for 8 nights.
  - *filler:* One moment.
  - *say:* Late November is a good call: the north is crisp and dry, and the south has settled after the rains. I'm already sketching something out. Where will you be flying from?
  - tools: prepare_trip
- **Traveller:** Beaches and food.
  - *filler:* Let me see.
  - *say:* Beaches and food is my kind of trip. Think Da Nang and Hoi An for the sand, with bowls of cao lầu and fresh seafood in between. And where will you be flying from?
  - tools: prepare_trip
- **Traveller:** From Madrid.
  - *filler:* Let me put that together.
  - *say:* Here's what I've put together: nine days from Hanoi down to the Mekong Delta, with a nonstop Iberia flight out of Madrid and a flight home from Saigon. It comes to about €2,770.81 all in. It's a wider route than the beaches-and-food trip you described. Hoi An is the sandy, food-heavy stretch, with a stay at the Nam Hai. I can slow it down and spend more nights on the coast if you'd like. There are also other flights home on the cards, including a cheaper nonstop. Which would you rather do?
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* Happy to. The airline needs a few details for each of you. Could you give me each traveller's title, full name as on the passport, and date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thank you, both of you are saved. Here's the booking: five hotels, from the Sofitel Metropole in Hanoi to the Park Hyatt in Saigon. You fly Iberia nonstop from Madrid on Saturday 21 November, and you come home with Qatar Airways on Monday 30 November, with one stop. The total is €2,770.81. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Sending it to your phone.
  - *say:* The payment link is on your phone now, and Apple Pay works there. Once it's paid, I'll check that everything shows as booked and tell you. The total is €2,770.81.
  - tools: book
  - 📱 the payment link reached the phone

## 6 · travellers given up front

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid. The travellers are Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* One moment.
  - *say:* Here's what I've put together for you and Sam: nine days running from Hanoi down to the Mekong Delta. It has Hoi An's beaches and plenty of street food along the way. The flights are chosen and the whole trip comes to €2,770.81. Your details are saved, so we can book whenever you're ready. The flight cards have other options if you'd like a different flight home.
  - tools: propose_trip, save_travellers
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *filler:* Nearly there.
  - *say:* Here's the final picture, Tyler. It's five hotel stops from Hanoi down to Saigon, and the Iberia direct flight out of Madrid on Saturday 21 November, landing in Hanoi early on the 22nd. You fly home with Qatar Airways on Monday 30 November, with one stop. The total for you and Sam is €2,770.81. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, propose_trip, hold_booking
- **Traveller:** Yes.
  - *filler:* Mm, let me think.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Nothing is confirmed until it's paid, so tap through when you're ready. Once it goes through, I'll check that everything shows as booked.
  - tools: book
  - 📱 the payment link reached the phone

## 7 · not yet, then yes

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It's nine days from Hanoi down to Saigon, with Ha Long Bay, Hoi An's beaches and lanterns, and a lot of street food on the way. The flights are chosen: you leave Madrid on the 21st and land in Hanoi early on the 22nd. The whole trip comes to €2,770.81. The other flight options are on the cards if you'd like to look. Would you like me to change anything, or shall I book it?
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Before I can book, I need the airline details for both of you. For each person, what's the full name as it appears on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Mm, let me think.
  - *say:* Thanks, Tyler, I've got you and Sam down. Here's what I'd book: five hotels, from Hanoi down to Saigon. You fly Iberia direct from Madrid on Saturday 21 November. You come home with Qatar Airways on Monday 30 November, with one stop. The total is €2,770.81. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Hmm, not yet.
  - *filler:* Bear with me a second.
  - *say:* No rush, Tyler. What's giving you pause? If it's the flights, the hotels or the price, I can change any of them. Or if you'd just like to think it over, that's fine too.
- **Traveller:** OK, go ahead.
  - *filler:* Let me have a look.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid. Once you've paid, I'll check it's all gone through.
  - tools: book
  - 📱 the payment link reached the phone

## 8 · is it booked?

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together: a direct Iberia flight out of Madrid that lands in Hanoi early on the 22nd, and a flight home from Saigon on the 30th. Hotels and flights come to about €2,770.81 for the two of you. It's a lot of movement for eight nights, from Hanoi down to the Mekong. Since you want beaches and food, I'd stay longer in Hoi An and Saigon and drop one or two stops. Do you want me to slim it down? There's also a direct flight home that's quite a bit cheaper than the one I picked, if you'd like me to swap it.
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *filler:* Nearly there.
  - *say:* Happy to. The airline needs each traveller's title, full name as on the passport, and date of birth. Could you give me those for you and your companion?
  - tools: propose_trip, hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler. I have you and Sam down. Here's what I'd book: five hotels, from Hanoi through to Saigon. Iberia flies you direct from Madrid on Saturday 21 November, and Qatar Airways brings you home from Saigon on Monday 30 November with one stop. The total is €2,770.81. The hotel prices are estimates, but the flights are quoted. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Mm, let me think.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid. Once you've paid, I'll check the status and tell you it's confirmed.
  - tools: book
  - 📱 the payment link reached the phone
- **Traveller:** Is it booked?
  - *filler:* Let me check.
  - *say:* Not yet, Tyler. Seven items are still waiting on your payment, and nothing is booked until it goes through. The link is on your phone, and Apple Pay works there. Tell me once you've paid and I'll check again.
  - tools: get_status

## 9 · make it three of us

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It's a loop from Hanoi down to Saigon, with Hoi An's beach days and plenty of street food along the way. Your flights are included, and the whole trip for the two of you comes to about €2,770.81. You fly out on the 21st and land in Hanoi early on the 22nd. The Iberia direct home on the cards is cheaper than the Qatar flight I picked, so say the word if you'd like me to swap it. Would you like it more beach and less city?
  - tools: propose_trip
- **Traveller:** Actually, make it three of us.
  - *filler:* Let me see.
  - *say:* I've redone it for three of you. The route is the same, from Hanoi down to Saigon with beach days in Hoi An. Flights and stays are included, and the whole trip comes to about €3,676.22. The Iberia direct home is much cheaper than the Qatar flight I picked, so say the word if you'd like it swapped in.
  - tools: prepare_trip, propose_trip
- **Traveller:** Book it.
  - *filler:* Mm, let me think.
  - *say:* I'll just need each traveller's details for the airline: full name as on the passport, title, and date of birth for all three of you.
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982; and Alex Warren, Mr, born 5 May 1990.
  - *filler:* Bear with me a second.
  - *say:* Thanks, Tyler, I have all three of you down. It's five hotels from Hanoi to Saigon, with Iberia direct from Madrid on Saturday 21 November. The way home is Qatar Airways from Saigon on Monday 30 November, and the total for the three of you is €3,676.22. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Let me have a look.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Nothing is confirmed until it's paid, so tap through when you're ready and I'll check that it's gone through.
  - tools: book
  - 📱 the payment link reached the phone

## 10 · taps the flight home, total, book it

- **Traveller:** Hi, I'm Tyler. Two of us, Vietnam for 8 nights from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together, Tyler. It's a 9-day run from Hanoi down to the Mekong Delta, with Hoi An's beach time and plenty of eating along the way. The total is €2,770.81 for the two of you, with a direct Iberia flight out that lands in Hanoi on the morning of the 22nd. The flight home is a Qatar one-stopper from Saigon, and the cards show a direct Iberia option home that's quite a bit cheaper. Want me to swap that in?
  - tools: propose_trip
- **Traveller:** the Iberia flight home at 08:30
  - *filler:* Let me see.
  - *say:* That's swapped. The Iberia flight home leaves Saigon at 08:30 on the 30th, and the new total is €2,456.28. Shall I book it, or would you like to change anything first?
  - tools: choose_offer
- **Traveller:** What's the total now?
  - *filler:* Mm, let me think.
  - *say:* It's €2,456.28 for the two of you, with both flights and the stays included. Some of the hotel prices are estimates, while the flights are quoted. Want me to go ahead and book it?
  - tools: get_total
- **Traveller:** Book it.
  - *filler:* Bear with me a second.
  - *say:* I just need each traveller's details for the airline. For you and your companion, could you give me the full name as on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler, I've got you both saved. Here's what I'd book: five hotels from Hanoi down to Saigon, and Iberia direct flights out on Saturday 21 November and home on Monday 30 November. The total is €2,456.28. The hotel prices are estimates and the flights are quoted. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Let me have a look.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid. Once you've done that, I'll check that everything has gone through.
  - tools: book
  - 📱 the payment link reached the phone

## 11 · Ecuador, the full loop

- **Traveller:** Hi, I'm Tyler. Two of us, 12 days around Ecuador from 22 November, nature and food, flying from Madrid.
  - *filler:* One moment.
  - *filler:* Nearly there.
  - *say:* Here's what I've put together, Tyler: twelve days from the Andes through the cloud forest and the Amazon, finishing with Pacific flavours in Guayaquil. It's about €2,983.81 for the two of you with flights from Madrid. Have a look at the other flights too. There's a direct Iberia flight home that's cheaper than the one I picked, if you'd like me to swap it in.
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Happy to, Tyler. The airline needs each traveller's details first. For you and your companion, could I have the full name as it appears on the passport, the title, and the date of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler. Everything's saved for you and Sam. It comes to seven hotels across Ecuador, then Iberia direct from Madrid on Saturday 21 November, arriving early on the 22nd. You fly home with Qatar Airways from Guayaquil on Thursday 3 December, with one stop. The total is €2,983.81. The hotel prices are estimates, but the flights are quoted. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Sending it to your phone.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing's confirmed until it's paid. Once you've done that, I'll check it's all gone through.
  - tools: book
  - 📱 the payment link reached the phone

## 12 · Japan, the full loop

- **Traveller:** Hi, I'm Tyler. Two of us, 10 days around Japan from 22 November, temples and food, flying from Madrid.
  - *filler:* One moment.
  - *filler:* Nearly there.
  - *say:* Here's what I've put together, Tyler. You start in Tokyo for the temples around Asakusa, then go to Kyoto for the golden temples and Arashiyama. You finish in Osaka, where the food is the main event. There's a hotel for each stop, and the whole trip for the two of you comes to about €3,715. You'd fly Iberia direct from Madrid on the 21st and land in Tokyo early on the 22nd. The way home is a Qatar flight from Osaka with one stop. Iberia also has a direct flight home that's cheaper, so I can swap to that if you'd like. The other flights are on the cards if you want to look.
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Happy to. For the airline I need each traveller's title, full name as on the passport, and date of birth, for you and your travel companion.
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, both of you are saved. Here's what I'd book: three hotels (Tokyo, Kyoto and Osaka), Iberia direct from Madrid on Saturday 21 November, and Qatar Airways home from Osaka on Tuesday 1 December with one stop. The total is €3,715.21. The hotel prices are estimates, and the flights are quoted. Shall I go ahead?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Mm, let me think.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is confirmed until it's paid. Once you've done that, I'll check that everything has gone through.
  - tools: book
  - 📱 the payment link reached the phone

## 13 · Morocco, the full loop

- **Traveller:** Hi, I'm Tyler. Two of us, 8 days around Morocco from 22 November, markets and the desert, flying from Madrid.
  - *filler:* One moment.
  - *filler:* Nearly there.
  - *say:* I've put together a loop through Morocco for the two of you. It starts with the souks in Marrakech, then crosses the High Atlas to the Sahara at Merzouga, and ends in the medina in Fès. It comes to about €2,712 all in, with flights from Madrid. The flight home leaves from Fès, and there's a cheaper direct one on the cards if you'd like to swap. Have a look and tell me what you think.
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me check everything.
  - *say:* Happy to. The airline needs each traveller's details first. For both of you, I need the full name as on the passport, the title, and the date of birth.
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler. Here's what I have: four hotels across Marrakech, Aït Benhaddou, Merzouga and Fès. You fly out with Iberia on Saturday 21 November, landing in Marrakech in the early hours of the 22nd. You fly home with Qatar Airways from Fès on Sunday 29 November, with one stop. The total is €2,712.41. The flights are quoted prices, but the hotel prices are estimates. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Let me see.
  - *say:* The payment link is on your phone now, Tyler, and Apple Pay works there. Nothing is booked until it's paid. Once you've paid, I'll check the status and tell you when everything's confirmed.
  - tools: book
  - 📱 the payment link reached the phone

## 14 · Portugal, the full loop

- **Traveller:** Hi, I'm Tyler. Two of us, 7 days around Portugal from 22 November, wine and the coast, flying from Madrid.
  - *filler:* One moment.
  - *filler:* Nearly there.
  - *say:* Here's what I've put together, Tyler: Porto, then the Douro vineyards, then Cascais and Lagos on the Algarve coast. It comes to about €2,905.61 for the two of you. The flight out leaves Madrid on the 21st and lands in Porto early on the 22nd. The flight home is a Qatar Airways with one stop. There's a direct Iberia home on the cards that's a good deal cheaper, if you'd like me to switch it.
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Before I can book, the airline needs each traveller's details. For you and your travel companion, what are your full names as on your passports, your titles (Mr, Ms and so on), and your dates of birth?
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Noting those down.
  - *say:* Thanks, Tyler, I've got you and Sam down. There are four hotels across Porto, the Douro, Cascais and Lagos. You fly Iberia direct from Madrid on Saturday 21 November. The way home is Qatar Airways with one stop, on Sunday 29 November. The total is €2,905.61 for both of you. The hotel prices are estimates and the flights are quoted. Shall I go ahead and book?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Mm, let me think.
  - *say:* The payment link is on your phone now, Tyler. Apple Pay works there. Nothing is booked until you've paid, and once you have, I'll check the status and tell you.
  - tools: book
  - 📱 the payment link reached the phone

## 15 · Vietnam, the full loop

- **Traveller:** Hi, I'm Tyler. Two of us, 8 days around Vietnam from 22 November, beaches and food, flying from Madrid.
  - *filler:* One moment.
  - *say:* Here's what I've put together for you both: Hanoi, a night on Ha Long Bay, Hue, then Hoi An for the beach and the food, and Saigon to finish. It comes to about €2,650.81 all in, with a direct Iberia flight out that lands in Hanoi early on the 22nd. The flight home is the Qatar one with a stop, and there's a cheaper direct Iberia flight back among the other cards if you'd like it. Does that route feel right, or would you rather spend more time on the coast?
  - tools: propose_trip
- **Traveller:** Book it.
  - *filler:* Let me see.
  - *say:* Happy to. For the airline I need both travellers' details: full name as on the passport, title, and date of birth for you and for whoever's coming along.
  - tools: hold_booking!travellers_missing
- **Traveller:** Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982.
  - *filler:* Mm, let me think.
  - *say:* Thanks, Tyler, I've got you both down. This is what you'd be booking: five hotels along the route, the Iberia direct from Madrid on Saturday 21 November, which lands in Hanoi early on the 22nd, and the Qatar Airways flight home from Saigon on 29 November with one stop. The total is €2,650.81. The flights are quoted prices, but the hotel prices are estimates. Shall I go ahead and send the payment to your phone?
  - tools: save_travellers, hold_booking
- **Traveller:** Yes.
  - *filler:* Bear with me a second.
  - *say:* The payment link is on your phone now, and Apple Pay works there. Nothing is booked until you've paid. Once you have, I'll check that everything went through and tell you.
  - tools: book
  - 📱 the payment link reached the phone
