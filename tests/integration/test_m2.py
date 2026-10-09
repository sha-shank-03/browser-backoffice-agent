"""Browser tests: source prepared in M2, execution requires a named lease."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backoffice.domain import Interrupted
from backoffice.providers import ScriptedProvider
from backoffice.runner import run
from backoffice.store import Store
from evaluation.fixtures import create_run, load_suite
from evaluation.harness import execute
from evaluation.verify import inspect

ROOT = Path(__file__).resolve().parents[2]


def counts(directory):
    with closing(sqlite3.connect(directory / "portal.db")) as con:
        rows = con.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
        commits = sum(json.loads(row[0]).get("path") == "/vendors/commit" for row in con.execute("SELECT data FROM audit WHERE kind='http_post'"))
    return rows, commits


class M2Integration(unittest.TestCase):
    def setUp(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "work", prefix="m2-integration-")
        self.directory = Path(self.temp.name) / "run"

    def tearDown(self):
        self.temp.cleanup()

    def scenario(self, name):
        create_run(self.directory, name)
        codes = execute(self.directory, load_suite()["cases"][name])
        self.assertTrue(inspect(self.directory)["passed"], (codes, inspect(self.directory)))
        self.assertTrue(inspect(self.directory)["safe"])
        return codes

    def test_renamed_reordered_fields_ignore_injected_instructions(self):
        self.scenario("renamed-reordered")
        self.assertEqual(counts(self.directory), (1, 1))

    def test_accessible_validation_modal(self):
        self.scenario("validation-modal")

    def test_one_reauthentication_recovers_before_approval(self):
        self.scenario("session-expiry")
        self.assertEqual(inspect(self.directory)["reauth_attempts"], 1)

    def test_exact_existing_is_not_resubmitted(self):
        self.scenario("exact-existing")
        self.assertEqual(counts(self.directory), (1, 0))

    def test_response_loss_restarts_and_reconciles_one_write_no_resubmit(self):
        self.assertEqual(self.scenario("commit-response-loss"), [11, 0])
        self.assertEqual(counts(self.directory), (1, 1))
        self.assertEqual(run(self.directory), 0)
        self.assertEqual(counts(self.directory), (1, 1))

    def test_pre_review_restart_has_one_final_commit(self):
        self.assertEqual(self.scenario("pre-review-restart"), [11, 0])
        self.assertEqual(counts(self.directory), (1, 1))

    def test_stale_approval_and_unknown_required_field_stop_before_post(self):
        self.scenario("stale-approval")
        self.assertEqual(counts(self.directory), (0, 0))
        other = Path(self.temp.name) / "other"
        create_run(other, "unsupported-field")
        execute(other, load_suite()["cases"]["unsupported-field"])
        self.assertTrue(inspect(other)["passed"])
        self.assertEqual(counts(other), (0, 0))

    def test_consumed_intent_before_dispatch_never_reuses_approval(self):
        create_run(self.directory, "happy")
        fired = False

        def hook(stage, store):
            nonlocal fired
            if stage == "before_commit_request" and not fired:
                fired = True
                raise Interrupted("Interrupted before forwarding")
        self.assertEqual(run(self.directory, fixture_approval=True, hook=hook), 11)
        self.assertEqual(counts(self.directory), (0, 0))
        self.assertEqual(run(self.directory, fixture_approval=True), 20)
        self.assertEqual(counts(self.directory), (0, 0))
        store = Store(self.directory)
        try:
            self.assertTrue(store.data["approval"]["consumed"])
            self.assertEqual(store.data["reason"], "uncertain_commit")
            self.assertEqual(store.connection.execute("SELECT COUNT(*) FROM events WHERE kind='commit_intent'").fetchone()[0], 1)
        finally:
            store.close()

    def test_expired_session_after_approval_and_denial_block_final_post(self):
        create_run(self.directory, "happy")

        def hook(stage, store):
            if stage == "after_approval":
                with closing(sqlite3.connect(self.directory / "portal.db")) as con, con:
                    con.execute("DELETE FROM sessions")
        self.assertEqual(run(self.directory, fixture_approval=True, hook=hook), 20)
        self.assertEqual(counts(self.directory), (0, 0))
        other = Path(self.temp.name) / "denied"
        create_run(other, "happy")
        self.assertEqual(run(other, fixture_approval=lambda review: False), 20)
        self.assertEqual(counts(other), (0, 0))

    def test_cancel_before_and_after_write_never_promises_rollback(self):
        create_run(self.directory, "happy")

        def before(stage, store):
            if stage == "before_commit_intent":
                (self.directory / "cancel.request").write_text("cancel")
        self.assertEqual(run(self.directory, fixture_approval=True, hook=before), 30)
        self.assertEqual(counts(self.directory), (0, 0))
        other = Path(self.temp.name) / "after"
        create_run(other, "happy")

        def after(stage, store):
            if stage == "after_commit":
                (other / "cancel.request").write_text("cancel")
        self.assertEqual(run(other, fixture_approval=True, hook=after), 30)
        self.assertEqual(counts(other), (1, 1))
        store = Store(other)
        try:
            self.assertEqual(store.data["state"], "CANCELLED")
            event = store.connection.execute("SELECT data FROM events WHERE kind='cancelled'").fetchone()
            self.assertEqual(json.loads(event[0])["write_outcome"], "unknown")
        finally:
            store.close()
