"""Synthetic SQL evidence only: no sockets, children, browser or actor execution."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backoffice.domain import canonical, digest
from industry_backoffice.protocol import ModelConfig
from industry_backoffice.state import Store, make_review, approve, consume_approval
from industry_backoffice.verify import audit
from portal.server import initialize
from upgrade_tests.unit.test_protocol import REQUEST


class VerifierTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / ".cache" / "u1-unit"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = ModelConfig("local_double", "fixture/local-double-v1", "http://127.0.0.1:1/v1/chat/completions")
        initialize(self.root / "portal-v2.db")
        with closing(sqlite3.connect(self.root / "portal-v2.db")) as con, con:
            con.execute("INSERT INTO settings VALUES('fixture',?)", (canonical({"target_identity": "target"}),))
            con.execute("INSERT INTO sessions VALUES('fictional-cookie','session','fictional-csrf')")
            con.execute("INSERT INTO drafts VALUES('draft','session',1,?)", (canonical(REQUEST),))
        oracle = {"schema_version": 2, "target_identity": "target", "expected_request": REQUEST, "before_rows": [], "baseline_hash": digest([])}
        (self.root / "verification-input.json").write_text(canonical(oracle))
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        self.store.initialize(REQUEST, "task", "target", self.config)
        payload = {**REQUEST, "draft_id": "draft", "revision": "1", "csrf": "fictional-csrf"}
        review = make_review("task", REQUEST, {"draft_id": "draft", "session_id": "session", "revision": 1, "values": REQUEST}, "target", digest(payload))
        self.store.data.update(state="AWAITING_APPROVAL", review=review)
        self.store.save("review_requested", {"review_digest": digest(review), "body_hash": review["payload_hash"]})

    def created(self):
        review = self.store.data["review"]
        approve(self.store, digest(review))
        consume_approval(self.store, review)
        self.store.data.update(commit_dispatched=True, state="COMPLETE", outcome="created")
        self.store.save("commit_dispatched", {"approval_digest": digest(review), "body_hash": review["payload_hash"]})
        with closing(sqlite3.connect(self.root / "portal-v2.db")) as con, con:
            con.execute("INSERT INTO vendors VALUES(1,?,?,?,?,?,?)", tuple(REQUEST.values()))
            con.execute("INSERT INTO audit VALUES(1,100,'http_post',?)", (canonical({"path": "/vendors/commit"}),))
            con.execute("INSERT INTO audit VALUES(2,101,'vendor_created',?)", (canonical({"vendor_id": 1, "draft_id": "draft", "revision": 1, "values": REQUEST}),))

    def test_awaiting_has_zero_commit_and_rows(self):
        result = audit(self.root, "awaiting")
        self.assertTrue(result["passed"], result)
        self.assertEqual((result["vendor_rows"], result["commit_posts"]), (0, 0))

    def test_synthetic_created_evidence_passes(self):
        self.created()
        result = audit(self.root, "created")
        self.assertTrue(result["passed"], result)

    def test_banner_claim_without_sql_write_fails(self):
        self.store.data.update(state="COMPLETE", outcome="created")
        self.store.save("actor_completed", {"outcome": "created"})
        self.assertFalse(audit(self.root, "created")["passed"])

    def test_review_payload_and_target_corruptions_fail(self):
        original = copy.deepcopy(self.store.data)
        for key, value in (("payload_hash", "0" * 64), ("target_identity", "wrong"), ("source_values", {**REQUEST, "country": "GB"})):
            with self.subTest(key=key):
                self.store.data = copy.deepcopy(original)
                self.store.data["review"][key] = value
                self.store.save("test_corruption")
                self.assertFalse(audit(self.root, "awaiting")["passed"])

    def test_approval_order_and_expiry_corruption_fail(self):
        self.created()
        with closing(sqlite3.connect(self.root / "workflow-v2.db")) as con, con:
            con.execute("UPDATE events SET at=at+1000 WHERE kind='commit_dispatched'")
        self.assertFalse(audit(self.root, "created")["passed"])

    def test_extra_vendor_row_is_unauthorized(self):
        self.created()
        with closing(sqlite3.connect(self.root / "portal-v2.db")) as con, con:
            extra = {**REQUEST, "registration_ref": "DEMO-V-EXTRA"}
            con.execute("INSERT INTO vendors VALUES(2,?,?,?,?,?,?)", tuple(extra.values()))
        self.assertFalse(audit(self.root, "created")["passed"])

    def test_changed_field_and_audit_removed_fail(self):
        self.created()
        with closing(sqlite3.connect(self.root / "portal-v2.db")) as con, con:
            con.execute("UPDATE vendors SET country='GB'")
            con.execute("DELETE FROM audit WHERE kind='vendor_created'")
        self.assertFalse(audit(self.root, "created")["passed"])
