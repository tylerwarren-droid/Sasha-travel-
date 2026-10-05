# Sasha 156: no restaurants and no thumbnails, fixed

*5 Oct 2026. A founder-approved exception to the freeze. Commits aec3b08, a6221ac, e629e1d and 4903ee0. Pre-warmed at 21:39 CEST.*

## Causes (found through the chat screen, not the API)

1. **No restaurants.**
   - Typing "restaurant**s** in Madrid tonight" never reached the Google search. The plain-search pattern (Sasha 140) knew
     "restaurant", not "restaurants".
   - So the model answered from its hand-picked **Vietnam** list in every city ("A few great places to eat in Vietnam —
     Tam Vi…").
   - Sasha 155 tested "dinner for 2 …" through the API, which matched, so this was missed.
2. **No text box without the camera.** The root chat's composer was a picture that started the call ("Tap to start, then
   just talk or type…").
3. **No thumbnails.**
   - The cards **never** used Google's photos. Since Sasha 88 (2 Oct) they showed only the venue's own website picture,
     "never a Google photo". Nothing from today removed a Google photo.
   - Many sites have none, or are slow (1.6–4 s), so most cards had no picture.
   - The pre-warm before the fix: 0–2 photos per 3 cards.
4. **WhatsApp:** a second search while "Which one?" was open ("restaurants in Lisbon" after Madrid) got "Which one?" again.
5. **Railway logs, last 3 h:** no Places, photo or search errors. Every cause above was in the code, not the services.

## Fixes (all additions)

- **Search:** plurals and "places to eat" are searches, anywhere in the world: Madrid, Lisbon, New York, Tokyo and Hanoi
  are all real Google listings.
- **Text box:** a real text box on the root chat. Typing opens the conversation with no call, no mic and no camera; the mic
  button still starts the call.
- **Google Maps photos where the venue's own is missing:**
  - The search asks Google for each listing's first photo (a field already paid for in the same request).
  - The cards shown come back with the photo's URL, which takes 0.7 s at most; the chat fetches any that miss that.
  - Each is credited as "Photo: Google Maps · <author>", as Google's terms ask.
  - The venue's own picture still comes first. A logo or spacer of their own falls back to Google's photo.
  - The same applies to web hotel cards and to WhatsApp (their own if it comes within 0.8 s, else Google's).
- **WhatsApp:** a new search while the cards show starts that search. Refinements of the current search are unchanged.

## After: through the UI, timed from Enter

**Signed out** (a clean browser on project.kanoe.ai), as cards / first photo; every real card had a photo:
- Madrid: 2.9 s / 3.5 s (the first ask also creates the visitor's private account)
- Lisbon: 1.0 s / 1.2 s
- New York: 1.4 s / 1.9 s
- Tokyo: 1.2 s / 1.3 s
- Hanoi: 1.2 s / 1.3 s

**Signed in** (the founder's Chrome): Madrid 1.6 s, Lisbon 1.5 s / 2.5 s, New York 1.6 s, Tokyo 1.2 s, Hanoi 1.9 s.
- Each run showed 5 cards, and every real card had a photo.
- The fifth card is our own test venue, which has none.

**WhatsApp** (simulated new number, deleted after): every city returned 2 real cards plus our test venue, all real
cards with photos, in 1.9–3.0 s.

## Cleanup

- Two scratch guest accounts from the signed-out runs were deleted (0 left, verified).
- I left the founder's web chat back in Sasha's own mode. My Sasha 155 Me3 test had left it in RelocateMe, which is why
  "New York" was answered by RelocateMe.

## Not a product bug

In the controlled Chrome, the browser tool's clicks missed the box after it resized the window to 940×564. The page logs
show no event reached the box, and typing worked every time otherwise.
