# S-73 — Madrid venues that take bookings through their OWN website form (for the founder to approve one)

*Sasha tab, 2 Oct 2026 (Sasha 94 · 2). **Read only:** robots.txt first, never a booking platform (venue_read's guards),
nothing submitted, nothing stored.*

## How they were found

- **The search:** Google Places, for 6 kinds of restaurant in 6 neighbourhoods (Chamberí, Salamanca, Malasaña, Retiro,
  Chueca, Lavapiés). That gave **402** places with a website, of which **384** were read.
- **What each site's own pages showed:**
  - **152** have no booking form at all (phone or email only).
  - **142** book through a platform widget: CoverManager 96, TheFork 29, Restoo 9, Resy 4, and mixes.
  - **6** have a form that posts to another site (a widget), and 4 sites *are* a booking platform.
  - **9** have their own form, but it has a CAPTCHA, isn't a POST, or **requires a box to tick**. Sasha stops at all
    of those, so they are excluded.
  - **6** have their own form with none of those problems. The three below are the clean ones.
- **Excluded from the six:**
  - La Canibal: a *groups* form, with an anti-spam field whose name changes on every load.
  - Pinocchio: a required menu choice Sasha can't map without asking.
  - Asador Nuevo Porche: in Barajas, with no legal page found.

## The three, for one to be approved

| | **Hanakura** (Japanese) | **Just Italia Chamberí** | **Florentine Madrid** (rooftop Italian) |
|---|---|---|---|
| Where | C/ de Murillo 4, Chamberí | Gta. de Ruiz Giménez 3, Chamberí | C. de Serrano 52, Salamanca |
| Google | ★ 4.4 (1,707) | ★ 4.3 (856) | ★ 4.6 (1,274) |
| The form | `hanakura.es/solicitar-reserva.html`, plain HTML, POSTs to itself | `justitalia.es/`, WordPress Contact Form 7, POSTs to itself | `florentinerestaurants.com/madrid`, POSTs to itself |
| Its fields | nombre, teléfono, email, comensales, fecha, hora, menú (select) | your-name, your-email, phone, people, start-date, ontime, **local** (which restaurant), special-requests | Name, Email, Phone, *Antal Gæster* (guests, a Danish CMS), date, time, Message |
| CAPTCHA / box to tick | none / none | none / none | none / none |
| robots.txt | none (404): all allowed | Yoast default, `Disallow:` empty: all allowed | sitemap only: all allowed |
| Terms read | `aviso-legal.html`: **nothing about automated use** | `politica-de-privacidad`: only a cookie that tells humans from bots **on blog comments** | **no legal page found** at the usual paths |
| What it is | a *request* ("solicitar reserva"): their answer page will say received, not confirmed | a booking request form | a booking form |
| To map | `menú` must have an exact option, or it is left empty if optional | `local` must be "Chamberí" exactly | the field names as they are |

**The tab recommends Hanakura.** It is the plainest form: one page, no WordPress JavaScript path, every field maps
(menú aside), its terms say nothing against automated use, and it is in Chamberí. Its answer is a *request*, so
the reservation stays **requested** until they confirm. That is honest, and the receipt says so.

## What approval sets in motion (nothing until the founder says the host)

1. A field map for that host in `form_rung.FORM_MAPS` (the names above, by role), committed through the gate.
2. `SASHA_FORM_HOSTS=<host>` and `SASHA_FORMS_ENABLED=1` on Railway.
3. A real booking for the founder, by his choice of date, read back field by field before his yes. The venue's
   answer page is kept word for word, and his receipt is emailed.
4. Afterwards, `SASHA_FORMS_ENABLED` goes back off until the next approved use.
