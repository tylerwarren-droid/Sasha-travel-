"""S-69 · before the move to a new Supabase project: a new `sb_secret_…` key goes as `apikey` only (Supabase refuses it
as a Bearer token), a legacy JWT key in both; and a refused prompt_versions read is SAID, never read as "no prompts".

    cd backend && python -m unittest tests.test_s69_service_keys -v
"""
from __future__ import annotations

import asyncio
import importlib
import os
import unittest
from unittest import mock


def headers_of(module_name: str, key: str) -> dict:
    with mock.patch.dict(os.environ, {"SUPABASE_SERVICE_KEY": key, "SUPABASE_URL": "https://new-ref.supabase.co"}):
        m = importlib.import_module(module_name)
        return importlib.reload(m)._HEADERS


class ServiceKeys(unittest.TestCase):
    def tearDown(self):
        for name in ("app.services.tenant", "app.services.prompts"):
            importlib.reload(importlib.import_module(name))   # back to the test environment's own values

    def test_a_new_secret_key_is_never_a_bearer(self):
        for module in ("app.services.tenant", "app.services.prompts"):
            self.assertEqual(headers_of(module, "sb_secret_abc123"), {"apikey": "sb_secret_abc123"}, module)

    def test_a_legacy_jwt_key_goes_in_both(self):
        for module in ("app.services.tenant", "app.services.prompts"):
            self.assertEqual(headers_of(module, "eyJhbGciOi.x.y"), {"apikey": "eyJhbGciOi.x.y", "Authorization": "Bearer eyJhbGciOi.x.y"}, module)


class PromptRead(unittest.TestCase):
    def test_a_refused_read_is_logged_and_the_static_prompts_stay(self):
        with mock.patch.dict(os.environ, {"SUPABASE_SERVICE_KEY": "sb_secret_x", "SUPABASE_URL": "https://new-ref.supabase.co"}):
            P = importlib.reload(importlib.import_module("app.services.prompts"))

            class R:
                status_code, text = 404, '{"message":"relation \\"public.prompt_versions\\" does not exist"}'

                def json(self):
                    raise AssertionError("a refused answer is never read as rows")

            class Client:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def get(self, url, params=None, headers=None, timeout=None):
                    self.seen = (url, headers)
                    return R()

            before = dict(P._cache)
            with mock.patch.object(P.httpx, "AsyncClient", Client), self.assertLogs("kanoe.prompts", "WARNING") as logs:
                asyncio.run(P._do_refresh())
            self.assertIn("prompt_versions read refused: HTTP 404", logs.output[0])
            self.assertEqual(P._cache, before)
        importlib.reload(importlib.import_module("app.services.prompts"))


if __name__ == "__main__":
    unittest.main()
