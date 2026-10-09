"""Providers receive only public UI observations and typed tool schemas."""
from __future__ import annotations

from typing import Protocol
from urllib.parse import parse_qs, urlparse

from .domain import ALIASES, Decision, LABELS, TOOLS, ProtocolError, canonical


class DecisionProvider(Protocol):
    identity: str

    def next_decision(self, context: dict, tool_schemas: dict) -> dict: ...


def ask(provider: DecisionProvider, context: dict) -> Decision:
    if len(canonical(context).encode()) > 64 * 1024:
        raise ProtocolError("Provider context exceeds 64 KiB")
    decision = Decision.parse(provider.next_decision(context, TOOLS))
    refs = {c["ref"] for c in context["observation"]["controls"]}
    if "ref" in decision.arguments and decision.arguments["ref"] not in refs:
        raise ProtocolError("Reference is outside the current observation")
    if "observation_id" in decision.arguments and decision.arguments["observation_id"] != context["observation"]["id"]:
        raise ProtocolError("Stale observation ID")
    return decision


def action(tool, **args):
    return {"tool": tool, "arguments": args}


def unique_control(observation, labels):
    matches = [c for c in observation["controls"] if c["label"] in labels]
    return matches[0] if len(matches) == 1 else None


class ScriptedProvider:
    identity = "scripted:reactive-ui-v2"

    def next_decision(self, context: dict, tool_schemas: dict) -> dict:
        obs, request = context["observation"], context["request"]

        def click(label):
            control = unique_control(obs, (label,))
            return action("click", ref=control["ref"]) if control else action("handoff", reason="unexpected_ui")

        path = urlparse(obs["url"]).path
        if path == "/login":
            return click("Open fictional operator session")
        if path == "/vendors":
            search = unique_control(obs, ("Registration reference search",))
            if not search:
                return action("handoff", reason="unexpected_ui")
            if search["value"] != request["registration_ref"]:
                return action("fill_from_request", ref=search["ref"], field="registration_ref")
            if parse_qs(urlparse(obs["url"]).query).get("q") != [request["registration_ref"]]:
                return click("Search")
            if obs["records"]:
                if obs["records"] == [request]:
                    if context["state"] == "RECONCILING":
                        return click("Inspect matching vendor")
                    return action("finish", outcome="existing")
                return action("handoff", reason="conflicting_existing")
            if context["state"] == "RECONCILING":
                return action("handoff", reason="uncertain_commit")
            return click("Register a vendor")
        if path == "/vendors/new":
            known = {label for labels in ALIASES.values() for label in labels}
            if any(c["role"] in {"textbox", "combobox"} and c["label"] not in known for c in obs["controls"]):
                return action("handoff", reason="unsupported_required_field")
            for field, labels in ALIASES.items():
                entry = unique_control(obs, labels)
                if not entry:
                    return action("handoff", reason="unexpected_ui")
                if entry["value"] != request[field]:
                    tool = "choose_from_request" if entry["role"] == "combobox" else "fill_from_request"
                    return action(tool, ref=entry["ref"], field=field)
            return click("Review vendor")
        if path == "/vendors/validation":
            if not unique_control(obs, ("Continue to review",)):
                return action("handoff", reason="validation_rejected")
            return click("Continue to review")
        if path == "/vendors/review":
            tool = "submit_approved" if context["state"] == "APPROVED" else "request_review"
            return action(tool, observation_id=obs["id"])
        if path == "/vendors/detail" and obs["records"] == [request]:
            return action("finish", outcome="created")
        return action("handoff", reason="insufficient_evidence")


class FixedMacroProvider:
    """Canonical linear macro; same host gates, no adaptive UI or restart policy."""
    identity = "fixed-macro:canonical-v1"

    def __init__(self):
        self.cursor = 0

    def next_decision(self, context, tool_schemas):
        obs = context["observation"]
        sequence = [("click", "Open fictional operator session", None),
                    ("fill_from_request", "Registration reference search", "registration_ref"),
                    ("click", "Search", None), ("click", "Register a vendor", None)]
        sequence += [("choose_from_request" if f in {"country", "category", "payment_terms"} else "fill_from_request", label, f)
                     for f, label in LABELS.items()]
        sequence += [("click", "Review vendor", None), ("request_review", None, None),
                     ("submit_approved", None, None), ("finish", None, None)]
        if self.cursor == 3 and obs["records"]:
            return action("finish", outcome="existing") if obs["records"] == [context["request"]] else action("handoff", reason="conflicting_existing")
        if self.cursor >= len(sequence):
            return action("handoff", reason="insufficient_evidence")
        tool, label, field = sequence[self.cursor]
        self.cursor += 1
        if tool == "finish":
            return action(tool, outcome="created")
        if tool in {"request_review", "submit_approved"}:
            return action(tool, observation_id=obs["id"])
        control = unique_control(obs, (label,))
        if not control:
            return action("handoff", reason="unexpected_ui")
        return action(tool, ref=control["ref"], **({"field": field} if field else {}))
