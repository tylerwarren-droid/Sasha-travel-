# Sasha 140: performance for Wednesday

*4 Oct 2026. Commits 4de6647, 76045c4 (and CR 16's a–c, 621c30e, which keep this work).*

## How it was measured

- **Account and code:** the founder's account, in-process, running exactly the code the server runs.
- **Services:** real ones (Google Places, the venues' own sites, our test venue's form, Stripe TEST).
- **WhatsApp:** simulated; nothing was sent.
- **Grid:** 4 kinds (restaurant, hotel, spa, tattoo studio) × 3 cities (Madrid, Hoi An, Hanoi) × 2 rounds per step, so n = 6
  per kind.
- **Harness and raw numbers:** `docs/sasha/perf/` (`s140_perf.py` before, `s140_after.py` after; JSON results).

## Before → after (WhatsApp, warm cache after the pre-warm)

| Step | Before p50 / p95 | After p50 / p95 |
|---|---|---|
| Intent (deterministic) | 0.00 / 0.01 s | same |
| Venue search (Google) | 0.7–1.2 / ≤1.5 s | 0.8–1.2 / ≤1.5 s (Google, not cacheable) |
| Photos | 3.2–6.4 / **up to 17 s**, blocking | **0.0 / ≤1.0 s**: cards never wait longer than the 1 s budget |
| **Cards shown, restaurants** | **6.6 / 11.5 s** | **0.9 / 1.8 s** |
| **Cards shown, hotels** | **4.4 / 17.9 s** | **1.2 / 2.5 s** |
| **Cards shown, spas** | **7.3 / 17.8 s** | **0.9 / 1.9 s** |
| **Cards shown, tattoo studios** | **5.8 / 7.1 s** | **0.8 / 0.9 s** |
| Read-back (venue read of the pick) | 3–13 / **up to 27 s** | **1.3 / 1.4 s** (our recent read reused) |
| Booking (test venue: form sent, their page read) | 8.1 s | 8.1 s (the venue's own server) |
| Payment (Stripe TEST page made) | 0.9 s | 0.9 s |

- **Target met:** cards under 3 s on a warm cache. p95 is 2.5 s at worst (hotels: Google search 1.5 s + the 1 s photo
  budget).
- **Cold, without pre-warm:** cards are capped at search + 1 s ≈ 2–2.5 s, because photos no longer block. Photos that
  miss the budget follow as their own messages ("📷 name").

## What changed

1. **Cards never wait on photos.** WhatsApp sends the cards with the photos ready within `SASHA_PHOTO_WAIT_S` (1 s). Late
   ones follow 2 s later as their own named messages. The web cards already loaded photos on their own.
2. **Photo cache.** Each venue's own share-picture URL is cached by its website for 24 h, including "none". It isn't
   Google content, so it may be cached.
3. **Read reuse.** A recent read of the same listing by the same account is reused for `SASHA_READ_REUSE_H` (6 h). Its
   Google facts are re-read on the spot (places_terms), so a pick no longer re-fetches the venue's site.
4. **Pre-warm.** Ops page "Pre-warm (night before)", `demo.py prewarm`, or `POST /ops/demo/prewarm`.
   - What it does: runs the demo's 14 queries on the server and warms each venue's photos and the founder's venue reads
     (≈ 90 s).
   - **Do not redeploy after pre-warming:** the photo cache is in the server's memory.
5. **No model on the hot path.** Bare "spa in Madrid" / "tattoo studio in Hanoi" went to the model on the web and to the
   help reply on WhatsApp; it's now a deterministic search.
   - WhatsApp never calls the model.
   - On the web, hotels still go to the hotel-card path (the model's), about 1.2 s for conduct().
6. **Not cached, on purpose:** Google's search results. Its terms allow caching only place IDs, so each search still
   asks Google (about 1 s).

## Photo coverage (hotel, spa, tattoo, restaurant)

- Every kind uses the same rule as restaurants: the venue's own site's share image, never Google's.
- Coverage depends on the venue publishing one:
  - spas and tattoo studios: 2 of 3 cards;
  - restaurants: 1 of 3;
  - hotels: 0–1 of 3.
- Cards without one show as text, honestly. A card never waits for a photo.

## For the founder, the night before Wednesday

1. Ops page → **Pre-warm** (≈ 1–2 min).
2. Don't redeploy afterwards.
3. Reset the demo after rehearsing. Reset doesn't clear the warm caches.
