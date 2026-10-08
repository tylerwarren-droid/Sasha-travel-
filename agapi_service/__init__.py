"""AgAPI sandbox service (CR 57) — a private, TEST-MODE-ONLY AgAPI a partner can call: find → hold → request_approval → book →
status → proof → cancel. Reuses Sasha's engines (backend/: Duffel search via booking_signer.travel, venue search via
booking_signer.venue_read, canonical JSON via booking_signer.canonical) on recorded fixtures — never the agent loop, and 0 live
calls. The v1 contract is EU's (tab_messages "EU 201", in parts); until each part lands this skeleton follows EU 200's shape
(docs/ad/agapi-convergence.md): one Approval object bound to the read-back's sha256, given on the end user's own device after the
read-back was presented, with an expiry; durable idempotency; outages as outages; fetched text marked untrusted; per-key metering."""
