"""CR 65 · EU 212's demo script IN A BROWSER (Playwright), inside the Docker build: a real DIVE server on a local port, a real Chromium,
the sandbox and the taverna played by fakes (no network, no real phone). See dive_service/e2e_demo.py.

    python -m unittest dive_service.tests.test_e2e -v      (from the repo root; needs playwright + chromium)
"""
from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    HAVE_PW = True
except ImportError:
    HAVE_PW = False


@unittest.skipUnless(HAVE_PW, "Playwright isn't installed here — the Docker build's test stage has it")
class DemoInABrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uvicorn
        from dive_service import app as A, channels as CH, config, onboard as ON, sandbox as SB
        from dive_service.store import Store
        from dive_service.tests.fakes import FakeSandbox, FakeTaverna
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        A.use_store(Store(os.path.join(tempfile.mkdtemp(), "e2e.db")))
        real_fetch = ON._http_fetch

        async def fetch(url):
            if "/fixtures/taverna" in url:   # the taverna's form (dry-run): served by the fake, never the network
                return 200, '<form id="booking-form"><input name="date"><select name="time"></select><select name="party_size"></select><input name="name"></form>'
            return await real_fetch(url)
        cls.patches = [mock.patch.object(SB, "TRANSPORT", FakeSandbox(latency=0.3)), mock.patch.object(config, "SANDBOX_KEY", "agp_test_" + "x" * 32),
                       mock.patch.object(config, "PUBLIC_URL", cls.base), mock.patch.object(ON, "FETCH", fetch),
                       mock.patch.object(CH, "POST_FORM", FakeTaverna()), mock.patch.object(CH, "send_time", lambda now_utc, quiet, tz=None: now_utc)]
        for p in cls.patches:
            p.start()
        CH._HOLDS.clear()
        cls.server = uvicorn.Server(uvicorn.Config(A.app, host="127.0.0.1", port=port, log_level="warning"))
        threading.Thread(target=cls.server.run, daemon=True).start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        time.sleep(0.3)
        for p in cls.patches:
            p.stop()

    def test_the_five_minute_script_and_the_failure_beat(self):
        from dive_service import e2e_demo
        steps = []
        e2e_demo.run(self.base, "dive-local", log=steps.append)
        self.assertEqual(len(steps), 8, steps)
        self.assertIn("failure beat", steps[-2])


if __name__ == "__main__":
    unittest.main()
