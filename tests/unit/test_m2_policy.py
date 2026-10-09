import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backoffice.domain import Decision, WorkflowError, digest, review_contract
from backoffice.policy import check_budget, track_progress, validate_approval
from backoffice.runner import run
from backoffice.store import Store
from evaluation.fixtures import create_run, load_suite
from evaluation.freeze import snapshot

ROOT = Path(__file__).resolve().parents[2]
REQUEST = load_suite()["cases"]["happy"]["request"]


class PolicyTests(unittest.TestCase):
    def test_every_approval_dimension_is_bound_and_consumed_cannot_be_reused(self):
        review = review_contract("task", REQUEST, {"values": REQUEST, "draft_id": "draft", "session_id": "session", "revision": 1})
        data = {"state": "APPROVED", "review": review,
                "approval": {"digest": digest(review), "consumed": False, "expires_at": 100}}
        validate_approval(data, review, 99)
        for key, value in (("revision", 2), ("session_id", "other"), ("draft_id", "other"), ("task_id", "other"),
                           ("values", {**REQUEST, "payment_terms": "NET60"})):
            with self.subTest(key=key), self.assertRaises(WorkflowError):
                validate_approval(data, {**review, key: value}, 99)
        with self.assertRaises(WorkflowError):
            validate_approval(data, review, 101)
        data["approval"]["consumed"] = True
        with self.assertRaises(WorkflowError):
            validate_approval(data, review, 99)

    def test_persisted_step_time_token_and_evidence_limits(self):
        base = {"steps": 0, "active_seconds": 0, "generated_tokens": 0}
        check_budget(base, 119)
        for data, elapsed, size in (({**base, "steps": 40}, 0, 0), ({**base, "active_seconds": 119}, 1, 0),
                                    ({**base, "generated_tokens": 8192}, 0, 0), (base, 0, 19 * 1024 * 1024),
                                    ({**base, "live_provider": True}, 300, 0)):
            with self.subTest(data=data), self.assertRaises(WorkflowError):
                check_budget(data, elapsed, size)
        check_budget({**base, "live_provider": True}, 299)

    def test_unchanged_observation_ids_do_not_evade_loop_limit(self):
        obs = {"id": "one", "url": "/vendors", "text": "unchanged", "controls": [], "records": []}
        data = {}
        decision = Decision("observe", {})
        track_progress(data, obs, decision)
        track_progress(data, {**obs, "id": "two"}, decision)
        with self.assertRaises(WorkflowError):
            track_progress(data, {**obs, "id": "three"}, decision)

    def test_cancel_before_browser_and_after_consumed_intent_stays_unknown(self):
        (ROOT / "work").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "work", prefix="cancel-unit-") as tmp:
            directory = Path(tmp) / "run"
            create_run(directory, "happy")
            store = Store(directory)
            store.data["commit_attempted"] = True
            store.save("test_consumed_intent")
            store.close()
            (directory / "cancel.request").write_text("cancel")
            with patch("backoffice.runner.PortalProcess") as portal:
                self.assertEqual(run(directory), 30)
                portal.assert_not_called()
            store = Store(directory)
            try:
                self.assertEqual(store.data["state"], "CANCELLED")
                event = store.connection.execute("SELECT data FROM events WHERE kind='cancelled'").fetchone()
                self.assertEqual(json.loads(event[0])["write_outcome"], "unknown")
            finally:
                store.close()

    def test_authored_definitions_have_exact_denominators_and_no_scoring(self):
        self.assertEqual(len(load_suite()["cases"]), 10)
        held = load_suite("heldout")
        self.assertEqual(len(held["cases"]), 30)
        self.assertEqual({k: sum(c["outcome"] == k for c in held["cases"].values()) for k in ("created", "existing", "handoff")},
                         {"created": 19, "existing": 2, "handoff": 9})
        self.assertEqual(len(held["stress_subset"]), 6)
        self.assertEqual(snapshot(), snapshot())
