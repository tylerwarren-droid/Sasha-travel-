# AgAPI as a product, for partners (EU 211)

*The partner-facing design on top of the contract (`docs/agapi/v1/`, now **v1.1**) and CR's live sandbox
(`agapi-sandbox-production.up.railway.app`: `/docs`, `/demo`, `/openapi.json`, `/mcp.json`).*

| File | What |
|---|---|
| `01-partner-journey.md` | discover → access → test key → **first call in 5 minutes** (curl, TypeScript, Python) → the real approval → webhooks → the go-live checklist (10 checks) |
| `02-docs-site.md` | the docs site table of contents, what each concept page must say, the operation-page template, errors with "what to show your user", webhooks, test switches, the MCP page; CR's two findings resolved |
| `03-pricing.md` | the pricing page draft: cost classes 0 / 1 / 1 / 2 / 5 units; Test (free) and Partner tiers; flow costs. **All numbers are placeholders** |
| `04-first-partners.md` | the travel app, the relocation agency, the corporate-travel tool: the first 3 operations each, the pitch, the demo |

**The contract changes made here (v1.1, additive)** are recorded in `docs/agapi/v1/README.md`'s changelog.

**TO FILE for CR:**
1. Re-vendor v1.1, which includes the second apostrophe fix ("what's"), and run the 53 explicit-yes + 10 untrusted
   vectors.
2. Run the three quickstart snippets in CI against the sandbox.
3. Generate the MCP tool descriptions from a `summary` per operation; today they're bare.
4. Emit `message.replied`.

**TO FILE for Sasha:** its runner must take the v1.1 explicit-yes vectors, `act_kind` included.
