"""Canonical JSON — the exact bytes a booking-task signature is computed over.

It must match the booking helper's canonicaliser BYTE FOR BYTE (docs/sasha-contract/README.md §2.1). A
serialiser that differs by one byte produces a task that looks valid and is refused as
`task_signature_invalid`. The helper's is JavaScript, so every rule below is JavaScript's:

  * null / true / false as written
  * numbers: INTEGERS ONLY, as decimal. The contract's payload holds no other kind; a float that is not
    a whole number, NaN, Infinity, or an integer beyond ±(2**53 − 1) is REFUSED rather than formatted,
    because JavaScript and Python format those differently (1e21 is "1e+21" in JavaScript)
  * strings exactly as JavaScript's JSON.stringify: \\" \\\\ \\b \\f \\n \\r \\t; every other code point
    below U+0020 as \\u00xx (lower-case hex); a LONE surrogate as \\udxxx (lower-case); everything else
    literal — non-ASCII, "/", DEL, U+2028 and U+2029 included
  * arrays in order; objects with keys sorted in UTF-16 CODE-UNIT order (JavaScript's default sort),
    which is NOT Python's code-point order for characters beyond U+FFFF
  * no whitespace anywhere

Only dict (string keys), list/tuple, str, int, bool, None — and a float only when it is a whole number.
Anything else (a datetime, a set, bytes, a custom object) is refused: a date is an ISO string.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

MAX_SAFE_INTEGER = 2**53 - 1

_SHORT = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


class CanonicalError(ValueError):
    """The value cannot be canonicalised the way the helper would."""


def _string(s: str) -> str:
    out = ['"']
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        cp = ord(ch)
        if ch in _SHORT:
            out.append(_SHORT[ch])
        elif cp < 0x20:
            out.append("\\u%04x" % cp)
        elif 0xD800 <= cp <= 0xDBFF and i + 1 < n and 0xDC00 <= ord(s[i + 1]) <= 0xDFFF:
            # a well-formed surrogate PAIR held as two code units: literal, as JavaScript emits it
            out.append(chr(0x10000 + ((cp - 0xD800) << 10) + (ord(s[i + 1]) - 0xDC00)))
            i += 1
        elif 0xD800 <= cp <= 0xDFFF:
            out.append("\\u%04x" % cp)  # a LONE surrogate, escaped lower-case (ES2019 well-formed stringify)
        else:
            out.append(ch)
        i += 1
    out.append('"')
    return "".join(out)


def _utf16_key(k: str) -> bytes:
    """Sort key giving JavaScript's order: UTF-16 big-endian bytes compare as UTF-16 code units."""
    return k.encode("utf-16-be", "surrogatepass")


def canonical_json(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):  # bool is handled above
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalError(f"integer {value} is beyond ±(2**53 − 1); JavaScript cannot represent it exactly")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalError("non-finite number")
        if not value.is_integer():
            raise CanonicalError(f"{value!r} is not a whole number; the payload carries integers only")
        return canonical_json(int(value))
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        for k in value:
            if not isinstance(k, str):
                raise CanonicalError(f"object key {k!r} is not a string")
        keys = sorted(value.keys(), key=_utf16_key)
        return "{" + ",".join(_string(k) + ":" + canonical_json(value[k]) for k in keys) + "}"
    raise CanonicalError(
        f"{type(value).__name__} cannot be canonicalised — convert it first (a date is an ISO string)"
    )


def canonical_bytes(value: Any) -> bytes:
    """The signed bytes: canonical JSON as UTF-8. Lone surrogates are already escaped, so strict UTF-8 holds."""
    return canonical_json(value).encode("utf-8")


def digest(value: Any) -> str:
    """sha256 of the canonical bytes, lower-case hex — the task digest reports quote back."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
