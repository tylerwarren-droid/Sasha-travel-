"""CR 73 · THE REGISTRY SURVEY, wave 0 (EU 214, docs/agapi/registry/*) — registry operations in AgAPI on the certified core.

  Country → Register → Document type → Access route, and EVERY fact a cited claim (source_url + verbatim quote + read_at). A field with
  no claim behind it is "unknown" — never a guess. Built on a READ-ONLY export of AD's catalogue (data/ad_export.json: SELECTs only,
  nothing is written to AD's database) + Magellan's reads of the registers' own official pages (data/reads.json, read from the sandbox
  server: robots.txt first, AD's never-fetch list honoured, every quote checked word for word against the page it came from).

  model.py   the tables (registry_*), ids (rgr_ rdt_ rrt_ rcl_), claims (quote_sha256 / claim_sha256), the snapshot loader
  gate.py    what may be fetched: AD's never-fetch list (ported from scripts/discovery-crawler/guardrails.py), strict robots
             (an HTML "robots.txt" is unreadable = not allowed), the one-page fetch used by verify
  reader.py  Magellan read_site, purpose registry, for an official register's own pages → registers / documents / routes / facts
  plan.py    registry.obtain_plan's ranking (api.md §2) — a pure function; spec/ext/vectors/registry-plan.json pins it
  verify.py  registry.verify's drift rule (fresh / drifted / broken) — pure; spec/ext/vectors/registry-drift.json pins it
  ops.py     registry.countries / get / documents / obtain_plan / verify (Kanoe extensions; EU formalizes in 1.3)
  page.py    /registry — the sandbox demo: pick a country → its registers, documents and obtain plans, each fact with its source

registry.obtain is OFF: plans only. Nothing here buys, logs in, solves a CAPTCHA or submits anything for anyone.
(The package is `registers`, not `registry`: agapi_service/registry.py is EU's normative tables and keeps its name.)"""
