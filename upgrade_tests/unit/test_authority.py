from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from backoffice.domain import digest
from industry_backoffice.protocol import Halt, ModelConfig
from industry_backoffice.state import Store, ActiveClock, LIMITS, approve, consume_approval, make_review, reserve_call, settle_call
from industry_backoffice.transport import exchange
from upgrade_tests.unit.test_protocol import REQUEST


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / ".cache" / "u1-unit"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.addCleanup(self.store.close)
        self.config = ModelConfig("local_double", "fixture/local-double-v1", "http://127.0.0.1:1/v1/chat/completions")
        self.store.initialize(REQUEST, "task", "target", self.config)

    def review(self):
        review = make_review("task", REQUEST, {"values": REQUEST, "draft_id": "draft", "session_id": "session", "revision": 1}, "target", "a" * 64)
        self.store.data.update(review=review, state="AWAITING_APPROVAL")
        self.store.save("review_requested", {"review_digest": digest(review)})
        return review

    def test_manual_approval_and_one_consumption(self):
        review = self.review()
        approve(self.store, digest(review), now=100)
        consume_approval(self.store, review, now=101)
        self.assertTrue(self.store.data["approval"]["consumed"])
        self.assertTrue(self.store.data["commit_attempted"])
        with self.assertRaises(Halt):
            consume_approval(self.store, review, now=102)

    def test_each_review_binding_change_blocks_consumption(self):
        review = self.review()
        approve(self.store, digest(review), now=100)
        for key, value in (("target_identity", "other"), ("payload_hash", "b" * 64),
                           ("draft_id", "new"), ("session_id", "new"), ("revision", 2),
                           ("mapping_version", "changed"), ("source_values", {**REQUEST, "country": "GB"})):
            with self.subTest(key=key), self.assertRaises(Exception):
                consume_approval(self.store, {**review, key: value}, now=101)
        self.assertFalse(self.store.data["commit_attempted"])

    def test_wrong_digest_expiry_and_cancel(self):
        review = self.review()
        with self.assertRaises(Halt):
            approve(self.store, "wrong", now=100)
        approve(self.store, digest(review), now=100)
        with self.assertRaises(Halt):
            consume_approval(self.store, review, now=401)
        (self.store.run_dir / "cancel.request").touch()
        with self.assertRaises(Halt):
            consume_approval(self.store, review, now=101)

    def test_elapsed_persists_and_human_wait_is_excluded(self):
        now = [100.0]
        clock = ActiveClock(self.store, lambda: now[0])
        now[0] += 7
        clock.persist()
        now[0] += 10000  # No active clock during human approval wait.
        resumed = ActiveClock(self.store, lambda: now[0])
        self.assertEqual(resumed.elapsed(), 7)
        now[0] += 3
        resumed.persist()
        self.assertEqual(self.store.data["active_seconds"], 10)

    def test_cumulative_call_and_unknown_token_budget_across_reopen(self):
        clock = ActiveClock(self.store)
        for _ in range(16):
            reserve_call(self.store, self.config, clock)
            settle_call(self.store, None, None)
        self.store.close()
        self.store = Store(Path(self.temp.name))
        self.addCleanup(self.store.close)
        self.assertEqual(self.store.data["calls"], 16)
        self.assertEqual(self.store.data["usage_unavailable_calls"], 16)
        self.assertIsNone(self.store.data["cost_inr"])
        with self.assertRaises(Halt) as caught:
            reserve_call(self.store, self.config, ActiveClock(self.store))
        self.assertEqual(caught.exception.code, "token_budget")

    def test_known_usage_releases_unused_reservation(self):
        reserve_call(self.store, self.config, ActiveClock(self.store))
        settle_call(self.store, 12, True)
        self.assertEqual(self.store.data["reserved_output_tokens"], 12)
        self.assertEqual(self.store.data["generated_tokens"], 12)

    def test_ambiguous_pending_never_reserves_again(self):
        reserve_call(self.store, self.config, ActiveClock(self.store))
        with self.assertRaises(Halt) as caught:
            reserve_call(self.store, self.config, ActiveClock(self.store))
        self.assertEqual(caught.exception.code, "ambiguous_inference_requires_operator")
        self.assertEqual(self.store.data["calls"], 1)

    def test_limit_and_cancel_before_call(self):
        self.store.data["calls"] = LIMITS["calls"]
        with self.assertRaises(Halt):
            reserve_call(self.store, self.config, ActiveClock(self.store))
        self.store.data["calls"] = 0
        (self.store.run_dir / "cancel.request").touch()
        with self.assertRaises(Halt):
            reserve_call(self.store, self.config, ActiveClock(self.store))
        self.assertEqual(self.store.data["calls"], 0)

    def test_events_reject_raw_body_and_credential_keys(self):
        for key in ("authorization", "api_key", "raw_response", "csrf", "prompt"):
            with self.assertRaises(Halt):
                self.store.save("unsafe", {key: "must-not-be-logged"})
        self.store.export()
        self.assertNotIn("must-not-be-logged", (self.store.run_dir / "events-v2.jsonl").read_text())

    def test_gateway_disabled_without_spawn_or_credential_lookup(self):
        config = ModelConfig("gateway", "openai/gpt-4.1-mini", "https://ai-gateway.vercel.sh/v1/chat/completions")
        with self.assertRaises(Halt) as caught:
            exchange(config, b"{}", 0, lambda: False)
        self.assertEqual(caught.exception.code, "live_dispatch_disabled")
        self.assertFalse(caught.exception.sent)

    def test_double_credentials_rejected_before_spawn(self):
        with self.assertRaises(Halt) as caught:
            exchange(self.config, b"{}", 0, lambda: False, credential="not-a-real-key")
        self.assertEqual(caught.exception.code, "double_must_not_receive_credentials")
