from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backoffice.domain import WorkflowError, digest, review_contract, validate_request
from backoffice.runner import approve
from backoffice.store import Store, run_lock
from evaluation.fixtures import create_run
from evaluation.verify import inspect, readonly

ROOT = Path(__file__).resolve().parents[2]
REQUEST = json.loads((ROOT / "fixtures/requests/cedar.json").read_text())


class DomainTests(unittest.TestCase):
    def test_request_rejects_extra_fields_and_nonfictional_email(self):
        with self.assertRaises(WorkflowError):
            validate_request({**REQUEST, "approval": "yes"})
        with self.assertRaises(WorkflowError):
            validate_request({**REQUEST, "contact_email": "real@example.com"})

    def test_review_digest_binds_every_field_and_revision(self):
        draft = {"draft_id": "draft-1", "session_id": "session-1", "revision": 1, "values": REQUEST}
        review = review_contract("task-1", REQUEST, draft)
        self.assertNotEqual(digest(review), digest({**review, "revision": 2}))
        with self.assertRaises(WorkflowError):
            review_contract("task-1", REQUEST, {**draft, "values": {**REQUEST, "payment_terms": "NET60"}})


class StateTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "work", prefix="unit-")
        self.path = Path(self.temp.name)
        create_run(self.path, "happy")

    def tearDown(self):
        self.temp.cleanup()

    def test_exclusive_owner_lock(self):
        with run_lock(self.path):
            with self.assertRaises(WorkflowError):
                with run_lock(self.path):
                    pass
        self.assertFalse((self.path / "run.lock").exists())

    def test_approval_requires_complete_exact_digest(self):
        store = Store(self.path)
        review = review_contract(store.data["task_id"], REQUEST, {"draft_id":"draft-1", "session_id":"session-1", "revision":1, "values":REQUEST})
        store.data.update(state="AWAITING_APPROVAL", review=review)
        store.save("review_ready")
        store.close()
        with self.assertRaises(WorkflowError):
            approve(self.path, "0" * 64)
        approve(self.path, digest(review))
        store = Store(self.path)
        try:
            self.assertEqual(store.data["state"], "APPROVED")
            self.assertFalse(store.data["approval"]["consumed"])
            self.assertEqual(store.data["approval"]["kind"], "manual_cli")
        finally:
            store.close()

    def test_independent_verifier_rejects_fake_success_claim(self):
        store = Store(self.path)
        store.data.update(state="ACTOR_DONE", outcome="created")
        store.save("fake_success_banner", {"text": "Registration completed"})
        store.export()
        store.close()
        result = inspect(self.path)
        self.assertFalse(result["passed"])
        self.assertEqual(result["vendor_rows"], 0)
        self.assertFalse(result["checks"][0]["passed"])

    def test_verifier_connection_is_readonly(self):
        with closing(readonly(self.path / "portal.db")) as con:
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("DELETE FROM vendors")
