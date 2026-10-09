"""CR 66 · AgAPI's PUBLIC DOCS (docs_site.py), EU 211's table of contents: every link resolves; every operation of operations.json 1.2
(the Keep included) has its generated page with badges, a request, a response and its errors; all 36 error codes have "what to show
your user"; the quickstart page carries EU's snippets byte for byte; the webhook snippets verify EU's signature vectors.

    python -m unittest agapi_service.tests.test_docs -v      (from the repo root)
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from agapi_service import config  # noqa: F401
from agapi_service import docs_site as D
from agapi_service.registry import operations
from agapi_service.tests.test_service import Base


class DocsSite(Base):
    def test_every_page_and_every_internal_link_resolves(self):
        seen, todo = set(), ["/docs"]
        while todo:
            u = todo.pop()
            if u in seen:
                continue
            seen.add(u)
            r = self.client.get(u)
            self.assertEqual(r.status_code, 200, u)
            if u.startswith("/docs"):
                for href in re.findall(r"""href=["'](/docs[^"'#]*)""", r.text):
                    todo.append(href)
        for n in operations():
            self.assertIn(f"/docs/operations/{n}", seen, n)                                     # every operation is reachable
        self.assertGreaterEqual(len(seen), 9 + 8 + len(operations()))
        for u in ("/", "/docs/reference", "/openapi.json", "/mcp.json", "/collection.http", "/demo"):
            self.assertEqual(self.client.get(u).status_code, 200, u)                            # the existing pages, kept

    def test_operation_pages_are_generated_with_their_badges_and_errors(self):
        self.assertEqual(len(operations()), 29)
        for n, o in operations().items():
            t = html.unescape(self.client.get(f"/docs/operations/{n}").text)
            self.assertIn("needs the user's approval" if o["requires_approval"] else "no approval", t, n)
            self.assertIn("Idempotency-Key" if o["idempotent"] else "not idempotent", t, n)
            self.assertIn(f"cost: {o['cost_class']}", t, n)
            for c in o.get("errors") or []:
                self.assertIn(f"#{c}", t, (n, c))
        keep = self.client.get("/docs/operations/keep.use").text
        self.assertIn("never_raw", keep)
        self.assertIn("since 1.2", keep)

    def test_every_error_code_says_what_to_show_your_user(self):
        codes = json.loads((D.SPEC / "v1" / "error-codes.json").read_text())["codes"]
        self.assertEqual(len(codes), 36)
        t = self.client.get("/docs/errors").text
        for c in codes:
            self.assertIn(f"id='{c['code']}'", t)
            show, do = D.SHOW[c["code"]]
            self.assertTrue(show and do, c["code"])
            self.assertIn(html.escape(show), t)

    def test_the_quickstart_page_is_eus_text_byte_for_byte(self):
        t = html.unescape(self.client.get("/docs/quickstart").text)
        sec = D._section(D.journey(), "## Step 4", "## Step 5")
        for lang, body in re.findall(r"```(bash|ts|python)\n(.*?)```", sec, re.S):
            self.assertIn(body.rstrip("\n"), t, lang)
        self.assertIn("runs in the sandbox's CI", t)
        self.assertIn('key() { uuidgen | tr -d', t)                                                   # EU 213's fix, on the page

    def test_changelog_and_go_live(self):
        t = self.client.get("/docs/changelog").text
        for v in ("1.0", "1.0.1", "1.1", "1.2"):
            self.assertIn(f"<b>{v}", t)
        self.assertIn("checklist", self.client.get("/docs/go-live").text.lower())
        self.assertIn("Live is not open yet", self.client.get("/docs/test-and-live").text)


class WebhookSnippets(unittest.TestCase):
    """EU 211 §5: the verification snippets run against webhook-signature.json in CI."""
    VEC = json.loads((D.SPEC / "v1" / "vectors" / "webhook-signature.json").read_text())["cases"]

    def cases(self):
        for c in self.VEC:
            hdr = c.get("header") or c["expect"].get("header")
            yield c, hdr, c.get("received_at_unix", c["t"])                          # W-3: arrives 301 s later → stale

    def test_python(self):
        ns = {}
        exec(D.WEBHOOK_SNIPPETS["python"], ns)
        for c, hdr, now in self.cases():
            self.assertEqual(ns["verify"](c["secret"], hdr, c["raw_body"], now=now), c["expect"]["valid"], c["id"])
        c = self.VEC[0]
        self.assertFalse(ns["verify"](c["secret"], c["expect"]["header"], c["raw_body"], now=c["t"] + 301))   # stale
        self.assertFalse(ns["verify"](c["secret"], c["expect"]["header"], c["raw_body"] + " ", now=c["t"]))   # tampered

    def test_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node isn't installed here — the Docker build has it")
        d = tempfile.mkdtemp()
        open(f"{d}/verify.mjs", "w").write(D.WEBHOOK_SNIPPETS["node"])
        cases = [{"secret": c["secret"], "header": h, "raw": c["raw_body"], "now": n, "valid": c["expect"]["valid"]} for c, h, n in self.cases()]
        script = f"import {{ verify }} from './verify.mjs';\nconst cs = {json.dumps(cases)};\nlet bad = cs.filter(c => verify(c.secret, c.header, c.raw, c.now) !== c.valid);\n" \
                 "if (bad.length) { console.log(JSON.stringify(bad)); process.exit(1) } console.log('ok ' + cs.length);"
        open(f"{d}/run.mjs", "w").write(script)
        r = subprocess.run([node, f"{d}/run.mjs"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
