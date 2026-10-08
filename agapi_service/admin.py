"""Issuing by hand (Part 4 K6), run where the service's database and pepper live:
    python -m agapi_service.admin key "<customer name>" [label]     → a new account (or the existing one by name) + a key, printed ONCE
    python -m agapi_service.admin webhook "<customer name>" <https-url>  → the endpoint id + its whsec_ secret, printed ONCE
    python -m agapi_service.admin list                              → accounts and key PREFIXES only (never a secret)
    python -m agapi_service.admin revoke <key_id>"""
from __future__ import annotations

import sys

from . import webhooks as W
from .app import create_account, create_key
from .store import Store, ts


def _account(store: Store, name: str) -> str:
    row = store.one("select id from accounts where name = ?", name)
    return row["id"] if row else create_account(store, name)


def main(argv) -> int:
    store = Store()
    if len(argv) >= 2 and argv[0] == "key":
        print(create_key(store, _account(store, argv[1]), argv[2] if len(argv) > 2 else argv[1]))
    elif len(argv) == 3 and argv[0] == "webhook":
        eid, secret = W.add_endpoint(store, _account(store, argv[1]), argv[2])
        print(eid, secret)
    elif argv[:1] == ["list"]:
        for a in store.q("select * from accounts order by created_at"):
            keys = store.q("select key_id, prefix, state, label from api_keys where account = ?", a["id"])
            print(a["id"], a["name"], [(k["key_id"], k["prefix"] + "…", k["state"], k["label"]) for k in keys])
    elif len(argv) == 2 and argv[0] == "revoke":
        print(store.x("update api_keys set state = 'revoked', revoked_at = ? where key_id = ?", ts(), argv[1]), "revoked")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
