"""Mint a sandbox key for a customer — printed once, stored hashed:  python -m agapi_service.keys "Acme Ventures" """
from __future__ import annotations

import sys

from .core import create_key
from .store import Store

if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        sys.exit('usage: python -m agapi_service.keys "Customer name"')
    print(create_key(Store(), sys.argv[1].strip()))
