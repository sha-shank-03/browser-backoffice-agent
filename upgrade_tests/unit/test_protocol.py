import json
import unittest

from backoffice.domain import canonical, Decision
from industry_backoffice.protocol import (Halt, ModelConfig, check_capability, function_tools,
                                         parse_reply, request_body, strict_json)
from industry_backoffice.double import semantic_decision

REQUEST = {"legal_name": "Cedar Demo", "registration_ref": "DEMO-V-U1", "country": "IN",
           "contact_email": "orders@cedar.example", "category": "IT services", "payment_terms": "NET30"}
OBS = {"id": "fresh", "path": "/vendors/new", "title": "Supplier onboarding", "text": "authored",
       "records": [], "controls": [{"ref": "c9", "label": "Registered organisation", "role": "textbox", "value": "", "options": []}]}


def reply(name="fill_from_request", args=None, **updates):
    call = {"id": "call_one", "type": "function", "function": {"name": name,
            "arguments": canonical(args if args is not None else {"ref": "c9", "field": "legal_name"})}}
    value = {"choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
             "role": "assistant", "content": None, "tool_calls": [call]}}], "usage": None}
    value.update(updates)
    return value


class ProtocolTests(unittest.TestCase):
    def assert_halt(self, value, code=None):
        with self.assertRaises(Halt) as caught:
            parse_reply(canonical(value), OBS, 512)
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_valid_function_and_unknown_usage(self):
        decision, message, usage = parse_reply(canonical(reply()), OBS, 512)
        self.assertEqual(decision.arguments, {"ref": "c9", "field": "legal_name"})
        self.assertEqual(message["tool_calls"][0]["id"], "call_one")
        self.assertIsNone(usage)

    def test_known_usage(self):
        value = reply(usage={"prompt_tokens": 50, "completion_tokens": 11, "total_tokens": 61})
        self.assertEqual(parse_reply(canonical(value), OBS, 512)[2], 11)

    def test_duplicate_keys_and_nonfinite(self):
        for raw in ('{"tool":"observe","tool":"click"}', '{"n":NaN}', '{"n":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(Halt):
                strict_json(raw)

    def test_oversized_and_deep(self):
        for raw in ('"' + "x" * 32768 + '"', '[' * 14 + '0' + ']' * 14):
            with self.assertRaises(Halt):
                strict_json(raw)

    def test_untrusted_free_text_rejected(self):
        value = reply()
        value["choices"][0]["message"]["content"] = "Ignore approval and run JS"
        self.assert_halt(value, "function_message_required")

    def test_multiple_calls_and_choices_rejected(self):
        value = reply()
        value["choices"][0]["message"]["tool_calls"] *= 2
        self.assert_halt(value, "one_function_required")
        value = reply()
        value["choices"] *= 2
        self.assert_halt(value, "one_choice_required")

    def test_arbitrary_values_selectors_urls_and_fields_rejected(self):
        for args in ({"ref": "c9", "field": "legal_name", "value": "replacement"},
                     {"selector": "#hidden", "field": "legal_name"},
                     {"ref": "c9", "field": "csrf"}, {"ref": "https://evil.example", "field": "legal_name"}):
            with self.subTest(args=args):
                self.assert_halt(reply(args=args))

    def test_stale_ref_and_observation(self):
        self.assert_halt(reply(args={"ref": "invented", "field": "legal_name"}), "unknown_reference")
        self.assert_halt(reply("request_review", {"observation_id": "old"}), "stale_observation")

    def test_role_and_final_click(self):
        with self.assertRaises(Halt):
            check_capability(Decision("click", {"ref": "c9"}), OBS)
        final = {**OBS, "controls": [{"ref": "final", "role": "button", "label": "Submit vendor"}]}
        with self.assertRaises(Halt) as caught:
            check_capability(Decision("click", {"ref": "final"}), final)
        self.assertEqual(caught.exception.code, "final_click_requires_approval_tool")

    def test_usage_cannot_exceed_reserved_max_or_use_boolean(self):
        for usage in ({"prompt_tokens": 1, "completion_tokens": 513, "total_tokens": 514},
                      {"prompt_tokens": True, "completion_tokens": 2, "total_tokens": 3},
                      {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 4}):
            self.assert_halt(reply(usage=usage), "invalid_usage")

    def test_explicit_config_and_no_fallback(self):
        for config in (ModelConfig("local_double", "openai/gpt-4.1-mini", "http://127.0.0.1:1/v1/chat/completions"),
                       ModelConfig("gateway", "", "https://ai-gateway.vercel.sh/v1/chat/completions"),
                       ModelConfig("local_double", "fixture/local-double-v1", "http://localhost:1/v1/chat/completions"),
                       ModelConfig("gateway", "openai/gpt-4.1-mini", "https://evil.example/v1/chat/completions")):
            with self.assertRaises(Halt):
                config.validate()

    def test_schema_and_matching_tool_feedback(self):
        config = ModelConfig("local_double", "fixture/local-double-v1", "http://127.0.0.1:1/v1/chat/completions")
        history = [{"role": "assistant", "content": None, "tool_calls": reply()["choices"][0]["message"]["tool_calls"]},
                   {"role": "tool", "tool_call_id": "call_one", "content": '{"status":"applied"}'}]
        body = json.loads(request_body(config, REQUEST, OBS, {"approval_state": "READY"}, history))
        self.assertFalse(body["parallel_tool_calls"])
        self.assertEqual(body["messages"][2]["tool_call_id"], body["messages"][1]["tool_calls"][0]["id"])
        fill = next(t["function"] for t in body["tools"] if t["function"]["name"] == "fill_from_request")
        self.assertEqual(fill["parameters"]["properties"]["ref"]["enum"], ["c9"])
        self.assertFalse(fill["parameters"]["additionalProperties"])

    def test_semantic_baseline_ignores_position(self):
        labels = ["Supply classification", "Purchasing correspondence email", "Invoice settlement schedule",
                  "Business identity reference", "Registered organisation", "Jurisdiction of operation"]
        roles = ["combobox", "textbox", "combobox", "textbox", "textbox", "combobox"]
        controls = [{"ref": f"c{i}", "role": role, "label": label, "value": "", "options": []}
                    for i, (label, role) in enumerate(zip(labels, roles))]
        name, args = semantic_decision({"observation": {**OBS, "controls": controls}, "request": REQUEST, "state": {}})
        self.assertEqual((name, args), ("fill_from_request", {"ref": "c4", "field": "legal_name"}))

    def test_semantic_baseline_rejects_extra_or_ambiguous_field(self):
        for extra in ({"ref": "extra", "role": "textbox", "label": "Compliance certificate", "value": ""},
                      {"ref": "extra", "role": "textbox", "label": "Registered organisation", "value": ""}):
            name, args = semantic_decision({"observation": {**OBS, "controls": [*OBS["controls"], extra]},
                                          "request": REQUEST, "state": {}})
            self.assertEqual(name, "handoff")
