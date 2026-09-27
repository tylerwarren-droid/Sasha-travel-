"""Minting a booking task — the signer's issue path (contract §3). STILL UNMOUNTED: no route calls this.

`issue_booking_task` refuses, BY NAME and IN THIS ORDER, before it signs anything:

  1. the refusal-half guard (live only)   live_without_established_refusal · live_refusal_basis_not_accepted ·
                                          live_refusal_without_source · live_on_a_placeholder_refusal ·
                                          live_refusal_pattern_invalid · live_refusal_selector_unsupported
  2. the paired device                    no_paired_device
  3. the email check (live only)          no_confirmation_email · email_cannot_receive_confirmation
  4. the origin rules                     url_unparseable · not_https · url_outside_origin ·
                                          originates_on_our_server · unknown_step ·
                                          no_submit_on_the_device · no_reading_on_the_device
  5. the approval binding                 approval_void · approval_void_payload · approval_voice_without_words
  6. required fields                      required_field_empty
  7. time limits                          task_expired · task_lifetime_too_long

The order and every rule name match the reference signer the booking helper was built against; the
parity fixture tests/booking_signer_issue_cases.json holds this module to that reference case by case,
including cases that break two rules at once.

Two refusals exist HERE and nowhere downstream the way they do here: the email check (the helper never
sees whether an address can receive mail) and the paired-account check (the helper knows only its own
device). The refusal-half guard is also re-run on the device.

⚠ A regex caveat, stated rather than hidden. Spec patterns are JavaScript regular expressions; this
module can only compile them with Python's `re`. The two engines agree on the patterns in use, but not on
every possible pattern — so a pattern Python accepts may still fail in the helper, which re-checks it and
refuses the task there. Python is the pre-check; the helper is the authority on its own regex engine.
"""
from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urlsplit

from .canonical import canonical_bytes, canonical_json
from .keys import LoadedSigningKey

# ── constants the helper also holds ──────────────────────────────────────────────────────────

#: Origins that are OURS: a task that would open one is the forbidden shape (contract §3.5 step 4).
OUR_ORIGINS = ("https://applieddiligence.com", "https://www.applieddiligence.com", "https://project.kanoe.ai")
#: The fixed step vocabulary. An unknown step is refused, never skipped.
BOOKING_STEPS = ("navigate", "await_form", "fill_fields", "submit", "read_page_after", "report")
#: A task lives at most this long (the helper's own ceiling).
MAX_TASK_LIFETIME_MS = 15 * 60_000
#: The bases a refusal half may rest on. Documentation is deliberately absent.
REFUSAL_BASES = ("observed_at_venue", "reference_install")

_PLACEHOLDER = re.compile(r"PLACEHOLDER|NOT\s+OBSERVED|NOT\s+a\s+reading", re.IGNORECASE)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class IssueRefused(Exception):
    """A task was not signed. `rule` is the contract's name for why."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


def _sha256hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _iso_ms(dt: datetime) -> str:
    """JavaScript's toISOString: UTC, milliseconds, 'Z'."""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _parse_instant(s: Any) -> Optional[datetime]:
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def filled_values_lines(fields: Iterable[Mapping[str, str]]) -> str:
    """`${selector}=${value}` per field, sorted (UTF-16 order, as JavaScript sorts), joined by '\\n'."""
    lines = [f"{f['selector']}={f['value']}" for f in fields]
    return "\n".join(sorted(lines, key=lambda x: x.encode("utf-16-be", "surrogatepass")))


# ── 1 · the refusal-half guard ───────────────────────────────────────────────────────────────

def live_refusal_check(mode: str, spec: Mapping[str, Any], standing: Optional[Mapping[str, Any]]) -> Optional[tuple]:
    """None when the act may proceed; otherwise (rule, why). A dry run needs none of this."""
    if mode != "live":
        return None
    if not standing or standing.get("established") is not True:
        return ("live_without_established_refusal", "this venue's refusal wording is not established, so a refusal could read as 'unclear' or, at worst, as a table the user does not have")
    if standing.get("basis") not in REFUSAL_BASES:
        return ("live_refusal_basis_not_accepted", f"the refusal half rests on {standing.get('basis')!r}, not one of {REFUSAL_BASES}")
    if not str(standing.get("source") or "").strip():
        return ("live_refusal_without_source", "an established refusal half names where it was observed")
    refused = spec.get("refused") if isinstance(spec, Mapping) else None
    if not isinstance(refused, list) or not refused:
        return ("live_without_established_refusal", "the standing says established and the spec carries no refusal pattern")
    for r in refused:
        pattern, meaning = r.get("text_pattern") or "", r.get("meaning") or ""
        if _PLACEHOLDER.search(pattern) or _PLACEHOLDER.search(meaning):
            return ("live_on_a_placeholder_refusal", f"refusal pattern {pattern!r} is the named placeholder")
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error:
            return ("live_refusal_pattern_invalid", f"refusal pattern {pattern!r} does not compile")
        sel = r.get("selector")
        if sel is not None and not re.match(r"^#.+$", sel.strip()) and not re.match(r"^\.[A-Za-z0-9_-]+$", sel.strip()):
            return ("live_refusal_selector_unsupported", f"refusal container {sel!r} is neither #id nor a single .class")
    return None


# ── 3 · the email check ──────────────────────────────────────────────────────────────────────

_LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TLD = re.compile(r"^[a-z]{2,63}$")
_NON_DELIVERING_TLDS = ("test", "invalid", "example", "localhost", "local")
_NON_DELIVERING_DOMAINS = ("example.com", "example.net", "example.org")


def email_can_receive_confirmation(value: Any) -> tuple:
    """(True, None) or (False, why). No network request: a well-formed address on a real-looking domain
    passes and may still bounce. It catches what the venue's plugin lets through — a value that is not an
    address — and never guesses beyond that."""
    if not isinstance(value, str):
        return (False, "it is not text")
    v = value.strip()
    if not v:
        return (False, "it is empty")
    if v != value:
        return (False, "leading or trailing spaces")
    if len(v.encode("utf-16-le")) // 2 > 254:  # JavaScript counts UTF-16 units
        return (False, "longer than an address can be (254 characters)")
    at = v.rfind("@")
    if at < 1 or at != v.find("@"):
        return (False, "not exactly one @ with something before it")
    local, domain = v[:at], v[at + 1:].lower()
    if len(local) > 64 or not _LOCAL.match(local):
        return (False, "the part before the @ is not a valid mailbox name")
    labels = domain.split(".")
    if len(labels) < 2 or any(not _LABEL.match(l) for l in labels):
        return (False, "the part after the @ is not a domain name")
    tld = labels[-1]
    if not _TLD.match(tld):
        return (False, "the domain has no valid top-level part")
    if tld in _NON_DELIVERING_TLDS or any(domain == d or domain.endswith("." + d) for d in _NON_DELIVERING_DOMAINS):
        return (False, f"{domain} is reserved never to deliver mail")
    return (True, None)


# ── 4 · the one line: the request originates on the user's device ──────────────────────────────

def _origin_of(url: str) -> Optional[tuple]:
    """(scheme, origin) for an absolute URL, or None if it does not parse as one."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if not parts.scheme or not host or " " in url:
        return None
    scheme = parts.scheme.lower()
    default = {"https": 443, "http": 80}.get(scheme)
    origin = f"{scheme}://{host.lower()}" + (f":{port}" if port is not None and port != default else "")
    return (scheme, origin)


def assert_originates_on_device(task: Mapping[str, Any], our_origins: Iterable[str] = OUR_ORIGINS) -> None:
    url, origin = task.get("url"), task.get("origin")
    parsed = _origin_of(url) if isinstance(url, str) else None
    if parsed is None:
        raise IssueRefused("url_unparseable", f"{url!r} is not a URL")
    scheme, url_origin = parsed
    if scheme != "https":
        raise IssueRefused("not_https", f"{url} is not https")
    if url_origin != origin:
        raise IssueRefused("url_outside_origin", f"the task's origin is {origin} and its url is {url_origin} — compared as origins, never prefixes")
    if any(o.lower() == str(origin).lower() for o in our_origins):
        raise IssueRefused("originates_on_our_server", f"the task would open {origin}, which is ours — the request must leave the user's machine, never our server")
    steps = list(task.get("steps") or [])
    unknown = [s for s in steps if s not in BOOKING_STEPS]
    if unknown:
        raise IssueRefused("unknown_step", f"steps {unknown!r} are not in the fixed vocabulary")
    if "submit" not in steps:
        raise IssueRefused("no_submit_on_the_device", "the task has no submit step, so something other than the device would be submitting")
    if "read_page_after" not in steps:
        raise IssueRefused("no_reading_on_the_device", "the task does not read the page after, so the outcome would be inferred rather than read")


# ── the issue path ───────────────────────────────────────────────────────────────────────────

def issue_booking_task(
    *,
    task: Mapping[str, Any],
    read_back: Mapping[str, Any],
    approval: Mapping[str, Any],
    mode: str,
    device_id: str,
    standing: Mapping[str, Any],
    confirmation_email_field: str,
    now: datetime,
    key: LoadedSigningKey,
    paired_device_ids: Optional[Iterable[str]] = None,
) -> dict:
    """Refuse (IssueRefused) or return {payload, signature, digest}.

    `read_back` is {lines, read_back_sha256, filled_values_sha256}; `approval` is {by, how, at, said,
    read_back_sha256, filled_values_sha256}. `paired_device_ids` is the devices THIS ACCOUNT has paired;
    pass it whenever it is known — the helper cannot check account membership, only its own device.
    """
    if mode not in ("dry_run", "live"):
        raise IssueRefused("task_malformed", f"mode is dry_run or live, not {mode!r}")

    # 1 · the refusal-half guard — first, because it is the one that could hurt someone
    half = live_refusal_check(mode, task.get("spec") or {}, standing)
    if half:
        raise IssueRefused(*half)

    # 2 · the paired device
    if not isinstance(device_id, str) or not _HEX64.match(device_id):
        raise IssueRefused("no_paired_device", "a task names the one paired device it may run on; pair the browser first")
    if paired_device_ids is not None and device_id not in set(paired_device_ids):
        raise IssueRefused("no_paired_device", "that device is not one this account has paired")

    # 3 · the email check — a booking whose email cannot receive a confirmation is not a booking
    if mode == "live":
        field = next((f for f in task.get("fields") or [] if f.get("name") == confirmation_email_field), None)
        if field is None:
            raise IssueRefused("no_confirmation_email", f"the task sends no {confirmation_email_field!r} field, so no confirmation can reach the user")
        ok, why = email_can_receive_confirmation(field.get("value"))
        if not ok:
            raise IssueRefused("email_cannot_receive_confirmation", f"{why}; the venue's form may accept it, the confirmation could never arrive")

    # 4 · the origin rules
    assert_originates_on_device(task)

    # 5 · the approval binding
    if approval.get("read_back_sha256") != read_back.get("read_back_sha256") or approval.get("filled_values_sha256") != read_back.get("filled_values_sha256"):
        raise IssueRefused("approval_void", "the approval was given to different words or a different payload than this read-back")
    lines = list(read_back.get("lines") or [])
    if _sha256hex("\n".join(lines)) != read_back.get("read_back_sha256"):
        raise IssueRefused("approval_void", "the read-back's own hash does not match its lines")
    recomputed = _sha256hex(filled_values_lines(task.get("fields") or []))
    if recomputed != task.get("filled_values_sha256") or recomputed != approval.get("filled_values_sha256"):
        raise IssueRefused("approval_void_payload", "the fields in this task are not the payload that was approved")
    if approval.get("how") == "voice" and not str(approval.get("said") or "").strip():
        raise IssueRefused("approval_voice_without_words", "a spoken approval records what was said")
    if approval.get("how") not in ("button", "voice"):
        raise IssueRefused("approval_void", f"an approval is by button or voice, not {approval.get('how')!r}")

    # 6 · required fields — the stop before an intent
    filled = {f.get("name") for f in task.get("fields") or [] if str(f.get("value") or "").strip()}
    empty = [n for n in task.get("required") or [] if n not in filled]
    if empty:
        raise IssueRefused("required_field_empty", f"required and empty: {', '.join(empty)}")

    # 7 · time limits
    expires = _parse_instant(task.get("expires_at"))
    lifetime_ms = (expires - now).total_seconds() * 1000 if expires else None
    if lifetime_ms is None or not lifetime_ms > 0:
        raise IssueRefused("task_expired", f"the task expires at {task.get('expires_at')!r}, which is not after now")
    if lifetime_ms > MAX_TASK_LIFETIME_MS:
        raise IssueRefused("task_lifetime_too_long", f"the task would live {round(lifetime_ms / 60000)} minutes; the ceiling is 15")

    payload = {
        "v": 1, "kind": "sasha_booking_task", "mode": mode, "task": task, "device_id": device_id,
        "spec_standing": {"established": standing.get("established"), "basis": standing.get("basis"), "source": standing.get("source")},
        "read_back": {"lines": lines, "sha256": read_back.get("read_back_sha256")},
        "approval": {
            "by": approval.get("by"), "how": approval.get("how"), "at": approval.get("at"), "said": approval.get("said"),
            "read_back_sha256": approval.get("read_back_sha256"), "filled_values_sha256": approval.get("filled_values_sha256"),
        },
        "issued_at": _iso_ms(now), "expires_at": task.get("expires_at"),
    }
    data = canonical_bytes(payload)
    return {
        "payload": payload,
        "signature": base64.b64encode(key._private.sign(data)).decode("ascii"),
        "digest": hashlib.sha256(data).hexdigest(),
    }


__all__ = [
    "IssueRefused", "issue_booking_task", "live_refusal_check", "email_can_receive_confirmation",
    "assert_originates_on_device", "filled_values_lines", "OUR_ORIGINS", "BOOKING_STEPS", "canonical_json",
]
