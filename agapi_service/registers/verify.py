"""registry.verify's rule (EU 214 api.md §1, vectors registry-drift.json): the stored quote + the page as read NOW →
  fresh    the quoted sentence is still on the page (a whitespace/case/typographic-quote change is still fresh)
  drifted  the page was read, the sentence is gone
  broken   the page couldn't be read at a layer that isn't transport: tls · http (404/410) · robots (now refused) · content · policy
A transport failure (DNS, timeout, refused connection, 5xx) is NOT a state: registry.verify answers source_unreachable (retry). Never drifted."""
from __future__ import annotations

from typing import Optional

from ..magellan import _norm


def drift(quote: str, page_text: Optional[str], failure_layer: Optional[str] = None) -> dict:
    if failure_layer:
        return {"state": "broken", "quote_still_present": False, "failure_layer": failure_layer}
    q = _norm(quote)
    present = bool(q) and q in _norm(page_text or "")
    return {"state": "fresh" if present else "drifted", "quote_still_present": present}
