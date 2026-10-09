import json
from pathlib import Path
import unittest

from backoffice.domain import Decision, ProtocolError
from backoffice.providers import ScriptedProvider, ask

ROOT = Path(__file__).resolve().parents[2]
REQUEST = json.loads((ROOT / "fixtures/requests/cedar.json").read_text())


class LocalDouble:
    identity = "local-test-double"

    def __init__(self, decision):
        self.decision = decision

    def next_decision(self, context, tool_schemas):
        return self.decision


def context():
    return {"schema_version":1, "request":REQUEST, "state":"CREATED", "remaining_steps":40,
            "observation":{"id":"obs-1", "url":"http://127.0.0.1:8000/vendors", "title":"Vendor search", "text":"",
                           "controls":[{"ref":"c0", "role":"textbox", "label":"Registration reference search", "value":"", "options":[]}], "records":[]}}


class DecisionContracts(unittest.TestCase):
    def test_rejects_multiple_calls_unknown_tool_and_payload_invention(self):
        examples = [[], {"tool":"fetch", "arguments":{"url":"https://example.com"}},
                    {"tool":"fill_from_request", "arguments":{"ref":"c0", "field":"contact_email", "value":"evil@other.example"}},
                    {"tool":"fill_from_request", "arguments":{"ref":"c0", "field":"oracle"}}]
        for value in examples:
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                Decision.parse(value)

    def test_rejects_unknown_reference(self):
        with self.assertRaises(ProtocolError):
            ask(LocalDouble({"tool":"click", "arguments":{"ref":"c999"}}), context())

    def test_rejects_stale_observation(self):
        with self.assertRaises(ProtocolError):
            ask(LocalDouble({"tool":"request_review", "arguments":{"observation_id":"old-observation"}}), context())

    def test_scripted_policy_reacts_to_current_observation(self):
        current = context()
        provider = ScriptedProvider()
        self.assertEqual(ask(provider, current).tool, "fill_from_request")
        current["observation"]["controls"][0]["value"] = REQUEST["registration_ref"]
        current["observation"]["url"] += "?q=" + REQUEST["registration_ref"]
        current["observation"]["records"] = [{**REQUEST, "payment_terms":"NET60"}]
        decision = ask(provider, current)
        self.assertEqual(decision.tool, "handoff")
        self.assertEqual(decision.arguments["reason"], "conflicting_existing")
