"""Test doubles that speak the AgAPI sandbox's PUBLIC API shape (no agapi_service import): users.register, messages.send_whatsapp
(first contact → the template; approval_required → the approval), sandbox.simulate_approval, sandbox.simulate_reply, messages.replies.
And a fake supplier form (the taverna's) and a fetch that reads DIVE's own fake site through the app."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from dive_service import rules as R


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class FakeSandbox:
    def __init__(self, latency: float = 0.0):
        self.users, self.windows, self.replies, self.approvals, self.sent, self.down = {}, {}, [], {}, [], False
        self.latency = latency        # the browser test plays a real round trip's delay, so a race shows up here, not live

    async def __call__(self, op, body, headers):
        if self.latency:
            import asyncio
            await asyncio.sleep(self.latency)
        if self.down:
            raise ConnectionError("sandbox down")
        assert headers["Authorization"].startswith("Bearer agp_test_")
        f = getattr(self, op.replace(".", "_"))
        return 200, f(body, headers)

    def ok(self, result):
        return {"agapi": "1.1", "ok": True, "result": result}

    def err(self, code, details=None):
        return {"agapi": "1.1", "ok": False, "error": {"code": code, "message": code, **({"details": details} if details else {})}}

    def users_register(self, b, h):
        uid = self.users.setdefault(b["external_ref"], R.new_id("opr").replace("opr_", "usr_"))
        return self.ok({"end_user_id": uid})

    def messages_send_whatsapp(self, b, h):
        n = b["to"]["number"]
        if "text" in b and not self.windows.get(n):
            return self.err("invalid_input", {"rule": "whatsapp_first_contact"})
        apv = h.get("AgAPI-Approval-Id")
        if not apv:
            rb = "rb_" + secrets.token_hex(13).upper()
            self.approvals[rb] = None
            return self.err("approval_required", {"read_back_id": rb, "read_back": {"lines": ["…"]}})
        ref = "sbx_wamid_" + secrets.token_hex(6)
        self.sent.append({"to": n, "text": b.get("text"), "template": "text" not in b})
        return self.ok({"act_id": "act_x", "intent_id": "int_x", "evidence_id": "evd_x", "outcome": {"kind": "CONFIRMED", "reference": ref},
                        "message": {"from": "+15005550100", "to": {"number": {"text": n}}, "kind": "text" if "text" in b else "template",
                                    "body_sha256": R.text_sha256(b.get("text") or "template"), "sent_at": now()}})

    def sandbox_simulate_approval(self, b, h):
        return self.ok({"approval_id": "apv_" + secrets.token_hex(13).upper(), "state": "valid"})

    def sandbox_simulate_reply(self, b, h):
        rid = "rpl_" + secrets.token_hex(13).upper()
        self.replies.insert(0, {"reply_id": rid, "number": b["number"], "text": b["text"], "received_at": now()})
        self.windows[b["number"]] = True
        return self.ok({"reply_id": rid, "received_at": now(), "opted_out": False, "window_open_until": now()})

    def messages_replies(self, b, h):
        return self.ok({"replies": [{"reply_id": r["reply_id"], "from": {"number": {"text": r["number"]}},
                                     "text": R.wrap(r["text"], "whatsapp_recipient", r["received_at"][:19] + "Z"), "received_at": r["received_at"]}
                                    for r in self.replies if r["number"] == b.get("number")]})


class FakeTaverna:
    """The taverna's form, as the sandbox hosts it: a confirmation with #reference, or a refusal (#refusal) the supplier means."""

    def __init__(self):
        self.posts, self.mode = [], "ok"

    async def __call__(self, url, fields):
        self.posts.append((url, dict(fields)))
        if self.mode == "down":
            return 502, "<h1>Bad gateway</h1>"
        if self.mode == "full":
            return 409, '<p id="refusal">Sorry — we&#x27;re full at 13:30 that day.</p>'
        return 201, '<div id="confirmation"><strong id="reference">TAV-1A2B3C</strong></div>'
