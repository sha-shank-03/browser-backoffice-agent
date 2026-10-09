"""Typed request, provider protocol and exact review contract."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

FIELDS = ("legal_name", "registration_ref", "country", "contact_email", "category", "payment_terms")
LABELS = dict(zip(FIELDS, ("Legal name", "Registration reference", "Country", "Contact email", "Category", "Payment terms")))
ALIASES = {
    "legal_name": ("Legal name", "Vendor legal name", "Registered business name"),
    "registration_ref": ("Registration reference", "Vendor reference", "Business reference"),
    "country": ("Country", "Operating country", "Country code"),
    "contact_email": ("Contact email", "Vendor email", "Order contact email"),
    "category": ("Category", "Vendor category", "Procurement category"),
    "payment_terms": ("Payment terms", "Invoice terms", "Settlement terms"),
}
HANDOFF_REASONS = {"conflicting_existing", "insufficient_evidence", "unexpected_ui",
                   "unsupported_required_field", "validation_rejected", "uncertain_commit"}
TOOLS = {
    "observe": (), "fill_from_request": ("ref", "field"),
    "choose_from_request": ("ref", "field"), "click": ("ref",),
    "request_review": ("observation_id",), "submit_approved": ("observation_id",),
    "finish": ("outcome",), "handoff": ("reason",),
}


class WorkflowError(Exception):
    """A bounded, operator-visible workflow failure."""


class ProtocolError(WorkflowError):
    pass


class Interrupted(WorkflowError):
    """Persisted interruption: resume without reusing consumed authority."""


class Cancelled(WorkflowError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def validate_request(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise WorkflowError("Request must contain exactly the six documented vendor fields")
    for key, text in value.items():
        if not isinstance(text, str) or not 1 <= len(text) <= 120 or text != text.strip():
            raise WorkflowError(f"Invalid bounded string for {key}")
        if any(ord(c) < 32 for c in text):
            raise WorkflowError(f"Control character in {key}")
    if not re.fullmatch(r"DEMO-V-[A-Z0-9-]{1,40}", value["registration_ref"]):
        raise WorkflowError("Only fictional DEMO-V- registration references are supported")
    if not re.fullmatch(r"[a-z0-9._+-]+@[a-z0-9.-]+\.example", value["contact_email"]):
        raise WorkflowError("Use a fictional lowercase .example contact address")
    if value["country"] not in {"IN", "GB", "US"}:
        raise WorkflowError("Unsupported country")
    if value["category"] not in {"Office supplies", "IT services"}:
        raise WorkflowError("Unsupported category")
    if value["payment_terms"] not in {"NET30", "NET60"}:
        raise WorkflowError("Unsupported payment terms")
    return dict(value)


@dataclass(frozen=True)
class Decision:
    tool: str
    arguments: dict[str, str]

    @classmethod
    def parse(cls, raw: Any) -> "Decision":
        if not isinstance(raw, dict) or set(raw) != {"tool", "arguments"}:
            raise ProtocolError("Decision must be one tool/arguments object")
        if len(canonical(raw).encode()) > 16 * 1024:
            raise ProtocolError("Decision exceeds 16 KiB")
        tool, args = raw["tool"], raw["arguments"]
        if not isinstance(tool, str) or tool not in TOOLS:
            raise ProtocolError("Unknown tool")
        if not isinstance(args, dict) or set(args) != set(TOOLS[tool]):
            raise ProtocolError("Unexpected tool arguments")
        if any(not isinstance(v, str) or not 1 <= len(v) <= 160 for v in args.values()):
            raise ProtocolError("Tool arguments must be bounded nonempty strings")
        if "field" in args and args["field"] not in FIELDS:
            raise ProtocolError("Unknown request field")
        if tool == "finish" and args["outcome"] not in {"created", "existing"}:
            raise ProtocolError("Unknown completion outcome")
        if tool == "handoff" and args["reason"] not in HANDOFF_REASONS:
            raise ProtocolError("Unknown handoff reason")
        return cls(tool, dict(args))


def review_contract(task_id: str, request: dict, draft: dict) -> dict:
    if draft.get("values") != request:
        raise WorkflowError("Displayed review does not match immutable request")
    if (any(not isinstance(draft.get(key), str) or not 1 <= len(draft[key]) <= 120 for key in ("draft_id", "session_id"))
            or type(draft.get("revision")) is not int or draft["revision"] < 1):
        raise WorkflowError("Missing review identity or revision")
    return {"schema_version": 1, "task_id": task_id, "request_hash": digest(request),
            "action": "create_vendor", "draft_id": draft["draft_id"],
            "revision": draft["revision"], "session_id": draft["session_id"], "values": dict(request)}
