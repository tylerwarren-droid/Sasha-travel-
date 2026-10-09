"""CR 64 · EU's ask: THE QUICKSTART RUN IN CI. The three snippets of EU's partner journey, step 4 (curl · TypeScript · Python —
spec/product/01-partner-journey.md, vendored byte for byte), run as published against a real sandbox server on a local port. The
ONE change: the production BASE URL becomes the local one. The curl snippet's placeholders (usr_…, off_…, rb_…, apv_…, hold_…,
evd_…) are filled from the previous step's answer, as a reader would. Each must end in a verified proof.

The Docker build runs this (curl, jq and Node 22 are in the image), so a snippet that drifts from the sandbox stops the deploy.

FOUND BY RUNNING THEM (CR 64, reported to EU): all three call sandbox.simulate_approval WITHOUT an Idempotency-Key, which EU's own
operations.json requires (idempotent: true) → step 4 fails with idempotency_key_required. Each test therefore checks BOTH: the
published snippet fails exactly there (when EU fixes the doc, that assertion fails — drop the erratum), and the snippet with that
ONE header added reaches a verified proof.
SECOND FINDING: the curl snippet's Idempotency-Keys are FIXED strings, so a partner who runs it twice gets idempotency_conflict at
trip.hold (a fresh offer id, the same key). The corrected run here therefore uses its own account (keys are scoped per account).

    python -m unittest agapi_service.tests.test_quickstart -v      (from the repo root)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from agapi_service import config  # noqa: F401  (puts backend/ on the path)

DOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "spec", "product", "01-partner-journey.md")
PROD = "https://agapi-sandbox-production.up.railway.app"


ERRATUM = "idempotency_key_required"   # sandbox.simulate_approval without an Idempotency-Key (EU's quickstart, 1.1)
FIX = {"python": ('"said": "Yes, book it."})', '"said": "Yes, book it."}, **{"Idempotency-Key": key()})'),
       "ts": ('said: "Yes, book it." });', 'said: "Yes, book it." }, { "Idempotency-Key": key() });'),
       "bash": ('$BASE/v1/sandbox.simulate_approval', '-H "Idempotency-Key: yes-marta-0000000001" $BASE/v1/sandbox.simulate_approval')}


def fixed(lang: str) -> str:
    a, b = FIX[lang]
    body = snippets()[lang]
    assert body.count(a) == 1, f"the {lang} snippet changed — re-check the erratum"
    return body.replace(a, b)


def snippets() -> dict:
    with open(DOC, encoding="utf-8") as f:
        text = f.read()
    step4 = text[text.index("## Step 4"):text.index("## Step 5")]
    return {lang: body for lang, body in re.findall(r"```(bash|ts|python)\n(.*?)```", step4, re.S)}


class Quickstart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uvicorn
        from agapi_service import app as A
        from agapi_service.store import Store
        cls.tmp = tempfile.mkdtemp()
        cls.store = Store(os.path.join(cls.tmp, "qs.db"))
        A.use_store(cls.store)
        cls.key = A.create_key(cls.store, A.create_account(cls.store, "Quickstart CI"), "quickstart")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.server = uvicorn.Server(uvicorn.Config(A.app, host="127.0.0.1", port=cls.port, log_level="warning"))
        threading.Thread(target=cls.server.run, daemon=True).start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(0.05)
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.env = {**os.environ, "AGAPI_KEY": cls.key}

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        time.sleep(0.2)

    def test_the_snippets_are_the_published_ones(self):
        s = snippets()
        self.assertEqual(set(s), {"bash", "ts", "python"})
        for body in s.values():
            self.assertIn(PROD, body)                                   # the only thing this test changes

    def run_python(self, body):
        return subprocess.run([sys.executable, "-c", body.replace(PROD, self.base)], env=self.env, capture_output=True, text=True, timeout=120)

    def test_python(self):
        r = self.run_python(snippets()["python"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(ERRATUM, r.stderr)                                # as published: step 4 (fix the doc → drop the erratum)
        r = self.run_python(fixed("python"))
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        out = r.stdout.strip().splitlines()
        self.assertTrue(out[-2].startswith(("AWAITING_PAYMENT evd_", "CONFIRMED evd_")), out)
        self.assertEqual(out[-1], "True", out)                          # the proof verifies

    def test_typescript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node isn't installed here — the Docker build has it")
        major, minor = (int(x) for x in subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()[1:].split(".")[:2])
        if (major, minor) < (22, 6):
            self.skipTest("Node < 22.6 can't strip TypeScript types")
        def run(body, name):
            path = os.path.join(self.tmp, name)
            with open(path, "w") as f:
                f.write(body.replace(PROD, self.base))
            return subprocess.run([node, "--experimental-strip-types", "--no-warnings", path], env=self.env, capture_output=True, text=True, timeout=120)
        r = run(snippets()["ts"], "published.mts")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(ERRATUM, r.stderr)                                # as published: step 4
        r = run(fixed("ts"), "fixed.mts")
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        out = r.stdout.strip().splitlines()
        self.assertEqual(out[-1], "true", out)

    def test_curl(self):
        with self.assertRaises(AssertionError) as e:                   # as published: step 4
            self.curl(snippets()["bash"], self.key)
        self.assertIn(ERRATUM, str(e.exception))
        with self.assertRaises(AssertionError) as e:                   # run again on the same account: the fixed keys collide
            self.curl(fixed("bash"), self.key)
        self.assertIn("idempotency_conflict", str(e.exception))
        from agapi_service import app as A
        self.curl(fixed("bash"), A.create_key(self.store, A.create_account(self.store, "Quickstart CI 2"), "quickstart-2"))

    def curl(self, body, key):
        if not shutil.which("curl"):
            self.skipTest("curl isn't installed here — the Docker build has it")
        work = tempfile.mkdtemp()
        path = os.environ.get("PATH", "")
        if not shutil.which("jq"):   # local runs only: the snippet's single `jq .result FILE`; the image has the real jq
            os.makedirs(os.path.join(work, "bin"))
            shim = os.path.join(work, "bin", "jq")
            open(shim, "w").write(f"#!{sys.executable}\nimport json,sys\nassert sys.argv[1]=='.result'\n"
                                  "print(json.dumps(json.load(open(sys.argv[2]))['result']))\n")
            os.chmod(shim, 0o755)
            path = os.path.join(work, "bin") + os.pathsep + path
        lines = body.replace(PROD, self.base).split("\n")
        pre = "\n".join(l for l in lines if l.startswith(("BASE=", "H=")))
        cmds, cur = [], []
        for l in lines:   # each curl command (with its continuation lines) is one step
            if l.startswith("curl "):
                cur = [l]
                cmds.append(cur)
            elif cur and (l.startswith(" ") or cur[-1].endswith("\\")) and not l.startswith("#"):
                cur.append(l)
            else:
                cur = []
        ids, out = {}, ""
        for c in cmds:
            cmd = "\n".join(c)
            for ph, slot in (("usr_…", "usr"), ("off_…", "off"), ("rb_…", "rb"), ("apv_…", "apv"), ("hold_…", "hold"), ("evd_…", "evd")):
                if ph in cmd:
                    self.assertIn(slot, ids, f"the snippet needs {ph} before any step gave one")
                    cmd = cmd.replace(ph, ids[slot])
            r = subprocess.run(["bash", "-c", pre + "\n" + cmd], cwd=work, env={**self.env, "AGAPI_KEY": key, "PATH": path}, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = r.stdout or (open(os.path.join(work, "evidence.json")).read() if "> evidence.json" in cmd else "")
            env = json.loads(out)
            self.assertTrue(env["ok"], (cmd[:80], env))
            res = env["result"]
            for k, v in (("usr", res.get("end_user_id")), ("off", ((res.get("offers") or [{}])[0]).get("offer_ref")),
                         ("rb", (res.get("read_back") or {}).get("read_back_id")), ("apv", res.get("approval_id")),
                         ("hold", res.get("hold_id")), ("evd", res.get("evidence_id"))):
                if v:
                    ids[k] = v
        self.assertTrue(json.loads(out)["result"]["valid"])            # the last step: the proof verifies


if __name__ == "__main__":
    unittest.main()
