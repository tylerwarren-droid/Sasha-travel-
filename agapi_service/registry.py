"""The normative tables, loaded from spec/v1 (the JSON wins over the prose): error-codes.json, operations.json and the schemas.
Inputs are validated against EU's own JSON Schemas (2020-12); tests validate every output and envelope the same way."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, Optional

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .rules import SPEC


@lru_cache(maxsize=1)
def errors() -> Dict[str, dict]:
    return {c["code"]: c for c in json.loads((SPEC / "error-codes.json").read_text())["codes"]}


@lru_cache(maxsize=1)
def operations() -> Dict[str, dict]:
    return {o["operation"]: o for o in json.loads((SPEC / "operations.json").read_text())["operations"]}


class AgapiError(Exception):
    """An error from the registry: its HTTP status, retryable and store_for_replay come from error-codes.json, never from here."""

    def __init__(self, code: str, message: str, details: Optional[dict] = None, retry_after_s: Optional[int] = None):
        if code not in errors():
            raise ValueError(f"not a registry code: {code}")
        super().__init__(message)
        self.code, self.message, self.details, self.retry_after_s = code, message, details or {}, retry_after_s

    @property
    def http(self) -> int:
        return errors()[self.code]["http"]

    @property
    def retryable(self) -> bool:
        return errors()[self.code]["retryable"]

    @property
    def store_for_replay(self) -> bool:
        return errors()[self.code]["store_for_replay"]

    @property
    def category(self) -> str:
        return errors()[self.code]["category"]

    def body(self) -> dict:
        e: Dict[str, Any] = {"code": self.code, "message": self.message, "retryable": self.retryable}
        if self.retry_after_s:
            e["retry_after_s"] = int(self.retry_after_s)
        if self.details:
            e["details"] = self.details
        return e


@lru_cache(maxsize=1)
def _registry() -> Registry:
    reg = Registry()
    for f in (SPEC / "schemas").rglob("*.json"):
        doc = json.loads(f.read_text())
        reg = reg.with_resource(doc["$id"], Resource.from_contents(doc))
    return reg


@lru_cache(maxsize=None)
def validator(ref: str) -> Draft202012Validator:
    """A validator for a schema ref ("…/tools.schema.json#/$defs/hold_in" or a whole schema's $id)."""
    return Draft202012Validator({"$ref": ref}, registry=_registry())


def schema_id(name: str) -> str:
    return {"response": "https://agapi.kanoe.dev/v1/schemas/response.schema.json",
            "read_back": "https://agapi.kanoe.dev/v1/schemas/read_back.schema.json",
            "approval": "https://agapi.kanoe.dev/v1/schemas/approval.schema.json",
            "error": "https://agapi.kanoe.dev/v1/schemas/error.schema.json"}[name]


def check_input(operation: str, value: Any) -> None:
    """additionalProperties false everywhere: an unknown field, a wrong type or a missing field → invalid_input {path, rule}."""
    errs = sorted(validator(operations()[operation]["input"]).iter_errors(value), key=lambda e: list(e.absolute_path))
    if errs:
        e = errs[0]
        path = "/" + "/".join(str(p) for p in e.absolute_path)
        raise AgapiError("invalid_input", f"The input doesn't match {operation}'s schema at {path}.",
                         {"path": path, "rule": e.validator})


def resolved(ref: str) -> dict:
    """The schema at `ref`, with every $ref inlined (for the MCP manifest and OpenAPI)."""
    reg = _registry()

    def walk(node: Any, base: str, depth: int = 0) -> Any:
        if depth > 40:
            return {}
        if isinstance(node, dict):
            if "$ref" in node:
                target = node["$ref"]
                full = target if target.startswith("http") else base.split("#")[0] + target
                r = reg.resolver().lookup(full)
                inner = walk(r.contents, full, depth + 1)
                rest = {k: walk(v, base, depth + 1) for k, v in node.items() if k != "$ref"}
                return {**inner, **rest} if rest else inner
            return {k: walk(v, base, depth + 1) for k, v in node.items() if k not in ("$id", "$schema")}
        if isinstance(node, list):
            return [walk(x, base, depth + 1) for x in node]
        return node
    return walk({"$ref": ref}, ref)
