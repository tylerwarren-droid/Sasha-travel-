"""CR 1 · one LIVE read of a PUBLISHED SPECIMEN passport through the real reader (docread._model_read) — never a real
person's passport. The key comes from Railway's environment (`railway run`); it is never printed.

    railway run python -m scripts.cr1_docread_live ../docs/products/specimen/NL-passport-specimen-2014-RvIG-CC0.jpg
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time

from products.relocation import docread as DR


async def main(path: str) -> None:
    small = tempfile.mktemp(suffix=".jpg")
    subprocess.run(["sips", "-Z", "1800", path, "--out", small], check=True, capture_output=True)   # well under the image cap
    data = open(small, "rb").read()
    t = time.monotonic()
    read = await DR._model_read(data, "image/jpeg")
    took = time.monotonic() - t
    print(json.dumps({"seconds": round(took, 1), "read": read, "check_digits": DR.verify(read), "facts": DR.to_facts(read),
                      "mrz": DR.mrz_check(read.get("mrz_line_2", ""))}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
