"""CR 77 · object storage for SOURCE COPIES — the Railway bucket "agapi-sources" (S3-compatible, EU West), AWS Signature V4, stdlib only.

  AGAPI_S3_ENDPOINT · AGAPI_S3_BUCKET · AGAPI_S3_REGION · AGAPI_S3_KEY_ID · AGAPI_S3_SECRET   (Railway variables; never printed)

Objects are CONTENT-ADDRESSED (the key carries the bytes' sha256), so a write never replaces different bytes: a re-read that got the same
bytes reuses the object, one that got new bytes adds a new one. With no bucket configured (tests, a laptop) objects live in memory."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from urllib.parse import quote, urlsplit

MEMORY: Dict[str, Tuple[bytes, str]] = {}   # key → (bytes, content-type) — only when no bucket is configured


def _cfg() -> Optional[dict]:
    keys = ("AGAPI_S3_ENDPOINT", "AGAPI_S3_BUCKET", "AGAPI_S3_KEY_ID", "AGAPI_S3_SECRET")
    if not all(os.environ.get(k) for k in keys):
        return None
    return {"endpoint": os.environ["AGAPI_S3_ENDPOINT"].rstrip("/"), "bucket": os.environ["AGAPI_S3_BUCKET"], "key": os.environ["AGAPI_S3_KEY_ID"],
            "secret": os.environ["AGAPI_S3_SECRET"], "region": os.environ.get("AGAPI_S3_REGION") or "auto"}


def configured() -> bool:
    return _cfg() is not None


def backend() -> str:
    return "bucket" if configured() else "memory"


def _host(c: dict) -> str:
    return f"{c['bucket']}.{urlsplit(c['endpoint']).hostname}"          # virtual-host style (the bucket's urlStyle)


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(c: dict, day: str) -> bytes:
    k = _sign(("AWS4" + c["secret"]).encode(), day)
    for part in (c["region"], "s3", "aws4_request"):
        k = _sign(k, part)
    return k


def _path(key: str) -> str:
    return "/" + quote(key, safe="/-_.~")


def _headers(c: dict, method: str, key: str, body: bytes, ctype: Optional[str] = None) -> Dict[str, str]:
    now = datetime.now(timezone.utc)
    amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    psha = hashlib.sha256(body).hexdigest()
    h = {"host": _host(c), "x-amz-content-sha256": psha, "x-amz-date": amz}
    if ctype:
        h["content-type"] = ctype
    names = sorted(h)
    creq = "\n".join([method, _path(key), "", "".join(f"{n}:{h[n]}\n" for n in names), ";".join(names), psha])
    scope = f"{day}/{c['region']}/s3/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(creq.encode()).hexdigest()])
    sig = hmac.new(_signing_key(c, day), sts.encode(), hashlib.sha256).hexdigest()
    h["authorization"] = f"AWS4-HMAC-SHA256 Credential={c['key']}/{scope}, SignedHeaders={';'.join(names)}, Signature={sig}"
    return h


async def exists(key: str) -> bool:
    c = _cfg()
    if not c:
        return key in MEMORY
    import httpx
    async with httpx.AsyncClient(timeout=30) as h:
        r = await h.head(f"https://{_host(c)}{_path(key)}", headers=_headers(c, "HEAD", key, b""))
    return r.status_code == 200


async def put(key: str, body: bytes, ctype: str) -> None:
    """Write once: an existing key (the same sha256, so the same bytes) is left as it is — never overwritten."""
    if await exists(key):
        return
    c = _cfg()
    if not c:
        MEMORY[key] = (body, ctype)
        return
    import httpx
    async with httpx.AsyncClient(timeout=120) as h:
        r = await h.put(f"https://{_host(c)}{_path(key)}", content=body, headers=_headers(c, "PUT", key, body, ctype))
    if r.status_code not in (200, 201):
        raise RuntimeError(f"the source copy wasn't stored (HTTP {r.status_code})")


async def get(key: str) -> bytes:
    c = _cfg()
    if not c:
        return MEMORY[key][0]
    import httpx
    async with httpx.AsyncClient(timeout=120) as h:
        r = await h.get(f"https://{_host(c)}{_path(key)}", headers=_headers(c, "GET", key, b""))
    if r.status_code != 200:
        raise RuntimeError(f"the source copy couldn't be read (HTTP {r.status_code})")
    return r.content


def presign(key: str, seconds: int = 600, filename: Optional[str] = None) -> str:
    """A short-lived signed GET URL (query-string SigV4). Memory backend: a memory: URL (tests only)."""
    c = _cfg()
    if not c:
        return f"memory://{key}"
    now = datetime.now(timezone.utc)
    amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    scope = f"{day}/{c['region']}/s3/aws4_request"
    q = {"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{c['key']}/{scope}", "X-Amz-Date": amz,
         "X-Amz-Expires": str(int(seconds)), "X-Amz-SignedHeaders": "host"}
    if filename:
        q["response-content-disposition"] = f'attachment; filename="{filename}"'
    qs = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(q.items()))
    creq = "\n".join(["GET", _path(key), qs, f"host:{_host(c)}\n", "host", "UNSIGNED-PAYLOAD"])
    sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(creq.encode()).hexdigest()])
    sig = hmac.new(_signing_key(c, day), sts.encode(), hashlib.sha256).hexdigest()
    return f"https://{_host(c)}{_path(key)}?{qs}&X-Amz-Signature={sig}"
