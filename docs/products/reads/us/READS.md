# CR 12 · the US Spanish consulates, read at source — 3 Oct 2026

Read by `backend/scripts/cr12_consulates_read.py` from exteriores.gob.es. robots.txt was read first (`robots-www.exteriores.gob.es.txt`: only /_layouts/, /_vti_bin/, /_catalogs/ disallowed); ≥ 10 s between requests; a 5xx was asked once more, later. The path to each page is the site's own: the ministry's directory of embassies and consulates → the consulate's home page → its Demarcación page and its services catalogue → *Visados Nacionales - Visado de residencia no lucrativa* via the catalogue's own parameters. Every page used is in this folder; its sha256 is in `backend/products/relocation/consulates_read.json` (the tests check each one).

Catalogue code: on the 5 consulates whose own links carry it, it equals the office's id in the ministry's directory; Chicago's and San Francisco's pages carry none, so the directory's id was used (recorded per consulate).

| consulate | its non-lucrative page | its list | appointment route on the page | territory from | its own additions |
|---|---|---|---|---|---|
| Consulado General de España en Nueva York | HTTP 200 `16c0beafa9d6…` | 10 items | email: cog.nuevayork.visnac@maec.es | its own page (23 de marzo de 2022) | yes |
| Sección Consular de la Embajada de España en Washington | HTTP 200 `29ac180b6f6d…` | 10 items | heading with nothing under it | the US consular network list on the Consulado General de España en Boston's page | none — the ministry template |
| Consulado General de España en Los Ángeles | HTTP 200 `1a40f2a86b8c…` | 10 items | heading with nothing under it | its own page | none — the ministry template |
| Consulado General de España en Miami | HTTP 200 `a1b0a5991c75…` | 10 items | heading with nothing under it | its own page | none — the ministry template |
| Consulado General de España en Chicago | HTTP 200 `fe967306d255…` | 10 items | heading with nothing under it | its own page | none — the ministry template |
| Consulado General de España en Houston | —  | 0 items | — | the US consular network list on the Consulado General de España en Boston's page | its home page answered HTTP 503 (asked twice, 10 s+ apart) |
| Consulado General de España en Boston | HTTP 200 `34afe7bb5bfc…` | 10 items | heading with nothing under it | the US consular network list on the Consulado General de España en Boston's page | none — the ministry template |
| Consulado General de España en San Francisco | HTTP 200 `cbf23c29fee9…` | 10 items | heading with nothing under it | the US consular network list on the Consulado General de España en Boston's page | none — the ministry template |

**What it means for the applicant.** New York's page is the only one adapted to its office: an appointment email (cog.nuevayork.visnac@maec.es) with six lettered items to send, the FBI record as the only accepted criminal record, what proves residence in its territory, and its fee sheet. The other six publish the ministry's template unchanged: the same 10 documents, the heading *Lugar de presentación* with nothing under it, and — on some — the template's unfilled field *“Campo para informar sobre el importe de la tasa de visado.”* (shown to the applicant as an unfilled field, never as a rule). Houston's site answered HTTP 503 twice, so no list from it.

**Two oddities, kept as the pages show them:** New York's item 1 link labelled *Formulario* opens its consular-fees sheet, not the visa form; the network list on Boston's page spells *West Virgina*.

**Every US page states the TIE rule:** *“se deberá solicitar la Tarjeta de Identidad de Extranjero en el plazo de 1 mes desde la entrada en España”* — the only reminder Sasha sets for a US file (none of their pages states London's 90-day window).
