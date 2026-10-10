"""CR 77 · SOURCE COPIES — every source a reader reads is KEPT as read: the original bytes (a PDF as the file; a web page as its HTML,
plus a PDF rendered from that HTML), each with its sha256, URL, date read and reader kind, in object storage (objects.py). A re-read adds
a new copy; nothing is ever overwritten (objects are content-addressed). Every quoted fact points to the copy it came from (copy_id).

  how     a reader runs inside `keeping(store, subject, kind)`; the fetchers (fineprint.reader, magellan) hand each 2xx body to capture().
  render  the HTML → PDF with WeasyPrint and NO network: the page's own markup only (no external CSS, images or scripts are fetched —
          a rendering never makes a request the reader didn't). Unavailable → the HTML copy stands and render_note says why.
  never   a failed copy never fails a read: the fact then has no copy, and Pacioli's check (d) sends it to the exceptions list."""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

from .. import objects as OB
from ..store import ts

log = logging.getLogger("agapi.copies")

TABLE = ("create table if not exists source_copies (id text primary key, subject text not null, url text not null, final_url text not null, "
         "reader_kind text not null, role text not null, read_at text not null, sha256 text not null, content_type text not null, "
         "size integer not null, object_key text not null, render_key text, render_sha256 text, render_note text, supplied_by text, "
         "of_url text, created_at text not null)")
_KEEPER: contextvars.ContextVar[Optional["Keeper"]] = contextvars.ContextVar("agapi_copy_keeper", default=None)


def ensure(store) -> None:
    store.x(TABLE)


def _ext(ctype: str, raw: bytes) -> str:
    if raw[:5] == b"%PDF-" or "pdf" in (ctype or "").lower():
        return "pdf"
    return "html" if "html" in (ctype or "html").lower() else "bin"


def _render_weasy(html: bytes, base_url: str) -> bytes:
    from weasyprint import HTML

    def no_fetch(url: str, *a, **k):   # the rendering never makes a request: only the page's own markup is drawn
        raise ValueError("external resources are not fetched")
    return HTML(string=html.decode("utf-8", "replace"), base_url=base_url, url_fetcher=no_fetch).write_pdf()


RENDER: Callable[[bytes, str], bytes] = _render_weasy   # tests replace it


def copy_id(subject: str, url: str, sha: str, read_at: str) -> str:
    return "scp_" + hashlib.sha256(f"{subject}|{url}|{sha}|{read_at}".encode()).hexdigest()[:24]


class Keeper:
    def __init__(self, store, subject: str, kind: str, *, role: str = "read", supplied_by: Optional[str] = None, read_at: Optional[str] = None):
        self.store, self.subject, self.kind, self.role, self.supplied_by = store, subject, kind, role, supplied_by
        self.read_at = read_at or ts()[:19] + "Z"
        self.kept: List[dict] = []
        self.notes: List[dict] = []   # official PDFs not kept, and why

    async def keep(self, url: str, final: str, ctype: str, raw: bytes, *, role: Optional[str] = None, of_url: Optional[str] = None) -> Optional[dict]:
        from .reader import clean_url
        hexsha = hashlib.sha256(raw).hexdigest()
        ext = _ext(ctype, raw)
        final_c = clean_url(final or url)
        rec: Dict[str, Any] = {"id": copy_id(self.subject, final_c, hexsha, self.read_at), "subject": self.subject, "url": clean_url(url),
                               "final_url": final_c, "reader_kind": self.kind, "role": role or self.role, "read_at": self.read_at,
                               "sha256": "sha256:" + hexsha, "content_type": "application/pdf" if ext == "pdf" else (ctype or "text/html").split(";")[0],
                               "size": len(raw), "object_key": f"sources/{hexsha[:2]}/{hexsha}.{ext}", "render_key": None, "render_sha256": None,
                               "render_note": None, "supplied_by": self.supplied_by, "of_url": of_url}
        try:
            await OB.put(rec["object_key"], raw, rec["content_type"])
        except Exception as e:
            log.error("[copies] not stored: %s: %s", type(e).__name__, e)
            return None
        if ext == "html":
            try:
                pdf = await asyncio.to_thread(RENDER, raw, final_c)   # CPU-bound: never on the event loop
                rs = hashlib.sha256(pdf).hexdigest()
                await OB.put(f"renders/{rs[:2]}/{rs}.pdf", pdf, "application/pdf")
                rec["render_key"], rec["render_sha256"] = f"renders/{rs[:2]}/{rs}.pdf", "sha256:" + rs
                rec["render_note"] = "rendered from the HTML as read; no external resources were fetched"
            except Exception as e:
                rec["render_note"] = f"no PDF rendering ({type(e).__name__}); the HTML copy stands"
        record(self.store, rec)
        self.kept.append(rec)
        return rec


def record(store, rec: dict) -> None:
    if store is None:
        return
    ensure(store)
    store.x("insert or ignore into source_copies (id, subject, url, final_url, reader_kind, role, read_at, sha256, content_type, size, object_key, "
            "render_key, render_sha256, render_note, supplied_by, of_url, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rec["id"], rec["subject"], rec["url"], rec["final_url"], rec["reader_kind"], rec["role"], rec["read_at"], rec["sha256"],
            rec["content_type"], rec["size"], rec["object_key"], rec.get("render_key"), rec.get("render_sha256"), rec.get("render_note"),
            rec.get("supplied_by"), rec.get("of_url"), ts())


@asynccontextmanager
async def keeping(store, subject: str, kind: str, **kw):
    k = Keeper(store, subject, kind, **kw)
    tok = _KEEPER.set(k)
    try:
        yield k
    finally:
        _KEEPER.reset(tok)


async def capture(url: str, final: str, status: int, ctype: str, raw: bytes) -> None:
    """Called by every fetcher: a 2xx body read while a keeper is set is kept. Never raises; robots.txt is not a source."""
    k = _KEEPER.get()
    if k is None or not (200 <= status < 300) or not raw or urlsplit(final or url).path.endswith("/robots.txt"):
        return
    try:
        await k.keep(url, final, ctype, raw)
    except Exception as e:
        log.error("[copies] capture failed: %s: %s", type(e).__name__, e)


def by_url(kept: List[dict]) -> Dict[str, dict]:
    """The copy each document URL came from (the latest of this read)."""
    out: Dict[str, dict] = {}
    for c in kept:
        out[c["final_url"]] = c
        out.setdefault(c["url"], c)
    return out


def get(store, cid: str) -> Optional[dict]:
    ensure(store)
    return store.one("select * from source_copies where id = ?", cid)


def for_source(store, subject: str, url: str, read_at: Optional[str] = None) -> Optional[dict]:
    """The copy a fact (or a registry claim) quoting `url` came from: the one kept at that read, else the latest before it."""
    ensure(store)
    rows = store.q("select * from source_copies where subject = ? and (final_url = ? or url = ?) and role != 'official_pdf' order by read_at desc",
                   subject, url, url)
    if read_at:
        rows = [r for r in rows if r["read_at"] <= read_at] or rows
    return rows[0] if rows else None
