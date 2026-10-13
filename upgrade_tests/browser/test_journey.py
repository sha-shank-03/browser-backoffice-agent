"""UNEXECUTED real Chromium/local-double checks; serial named lease only.

Approval commands in these tests simulate an operator explicitly accepting a displayed
digest. This is automation of the manual CLI boundary, not evidence of a human reviewer.
"""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backoffice.domain import digest
from industry_backoffice.__main__ import main, initialize_run
from industry_backoffice.protocol import ModelConfig
from industry_backoffice.state import Store
from industry_backoffice.verify import audit
from upgrade_tests.unit.test_protocol import REQUEST

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/local-double-v2.json"


class JourneyTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".cache/u1-browser"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        self.config = ModelConfig("local_double", "fixture/local-double-v1", "http://127.0.0.1:1/v1/chat/completions")

    def command(self, name, *extra):
        return main([name, "--run-dir", str(self.run), *extra])

    def start(self, **fixture_options):
        initialize_run(self.run, REQUEST, self.config, fixture_options=fixture_options)
        return self.command("resume", "--config", str(CONFIG))

    def simulated_operator_approve(self):
        store = Store(self.run)
        try:
            supplied = digest(store.data["review"])
        finally:
            store.close()
        self.assertEqual(self.command("review"), 0)
        self.assertEqual(self.command("approve", "--digest", supplied), 0)

    def test_semantic_layout_manual_cli_resume_independent_sql(self):
        self.assertEqual(self.start(), 10)
        self.assertTrue(audit(self.run, "awaiting")["passed"])
        self.simulated_operator_approve()
        self.assertEqual(self.command("resume", "--config", str(CONFIG)), 0)
        verified = audit(self.run, "created")
        self.assertTrue(verified["passed"], verified)
        self.assertEqual(verified["commit_posts"], 1)
        self.assertEqual(self.command("resume", "--config", str(CONFIG)), 0)
        self.assertEqual(audit(self.run, "created")["commit_posts"], 1)
        events = (self.run / "events-v2.jsonl").read_text()
        with closing(sqlite3.connect(self.run / "portal-v2.db")) as con:
            for token, csrf in con.execute("SELECT token,csrf FROM sessions"):
                self.assertNotIn(token, events)
                self.assertNotIn(csrf, events)
        self.assertFalse((self.run / "run.lock").exists())

    def test_exact_existing_never_commits(self):
        initialize_run(self.run, REQUEST, self.config, existing=True)
        self.assertEqual(self.command("resume", "--config", str(CONFIG)), 0)
        self.assertTrue(audit(self.run, "existing")["passed"])

    def test_unsupported_field_handoffs_without_write(self):
        self.assertEqual(self.start(unsupported_field=True), 20)
        self.assertTrue(audit(self.run, "handoff")["passed"])

    def test_cancel_after_review_blocks_resume(self):
        self.assertEqual(self.start(), 10)
        self.simulated_operator_approve()
        self.assertEqual(self.command("cancel"), 0)
        self.assertEqual(self.command("resume", "--config", str(CONFIG)), 21)
        self.assertTrue(audit(self.run, "cancelled")["passed"])

    def test_changed_review_revision_blocks_approved_submission(self):
        self.assertEqual(self.start(), 10)
        self.simulated_operator_approve()
        with closing(sqlite3.connect(self.run / "portal-v2.db")) as con, con:
            con.execute("UPDATE drafts SET revision=revision+1")
        self.assertEqual(self.command("resume", "--config", str(CONFIG)), 30)
        with closing(sqlite3.connect(self.run / "portal-v2.db")) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM vendors").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM audit WHERE kind='vendor_created'").fetchone()[0], 0)

    def test_changed_hidden_payload_blocks_dispatch(self):
        from industry_backoffice.browser import V2Browser
        from unittest.mock import patch
        self.assertEqual(self.start(), 10)
        self.simulated_operator_approve()
        original = V2Browser.arm_and_submit
        def changed(browser, review):
            browser.page.locator('form[action="/vendors/commit"] input[name="csrf"]').evaluate("el => el.value = 'changed'")
            return original(browser, review)
        with patch.object(V2Browser, "arm_and_submit", changed):
            self.assertEqual(self.command("resume", "--config", str(CONFIG)), 20)
        with closing(sqlite3.connect(self.run / "portal-v2.db")) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM vendors").fetchone()[0], 0)
            posts = [json.loads(row[0])["path"] for row in con.execute("SELECT data FROM audit WHERE kind='http_post'")]
            self.assertNotIn("/vendors/commit", posts)
