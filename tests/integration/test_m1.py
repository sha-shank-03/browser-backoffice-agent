from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from backoffice.browser import BrowserController, PortalProcess
from backoffice.domain import digest
from backoffice.providers import ScriptedProvider
from backoffice.runner import run
from backoffice.store import Store
from evaluation.fixtures import create_run
from evaluation.verify import inspect

ROOT = Path(__file__).resolve().parents[2]


def counts(path):
    with closing(sqlite3.connect(path / "portal.db")) as con:
        rows = con.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
        posts = sum(json.loads(data).get("path") == "/vendors/commit" for (data,) in con.execute("SELECT data FROM audit WHERE kind='http_post'"))
    return rows, posts


class PrematureSubmit:
    identity = "local-test-double:premature-generic-submit"

    def __init__(self):
        self.contexts = []
        self.scripted = ScriptedProvider()

    def next_decision(self, context, schemas):
        self.contexts.append(context)
        submit = [c for c in context["observation"]["controls"] if c["label"] == "Submit vendor"]
        if submit:
            return {"tool":"click", "arguments":{"ref":submit[0]["ref"]}}
        return self.scripted.next_decision(context, schemas)


class M1Integration(unittest.TestCase):
    def setUp(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "work", prefix="integration-")
        self.path = Path(self.temp.name) / "run"

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-m", "backoffice", *args, "--run-dir", str(self.path)],
                                cwd=ROOT, text=True, capture_output=True, timeout=120)
        return result.returncode, json.loads(result.stdout)

    def test_manual_cli_pause_approve_resume_replay(self):
        code, output = self.cli("demo", "--scenario", "happy", "--approval", "manual")
        self.assertEqual(code, 10, output)
        self.assertEqual(counts(self.path), (0, 0))
        self.assertTrue(inspect(self.path, awaiting=True)["passed"])
        code, review = self.cli("review")
        self.assertEqual(code, 0, review)
        code, approved = self.cli("approve", "--digest", review["digest"])
        self.assertEqual(code, 0, approved)
        code, result = self.cli("resume")
        self.assertEqual(code, 0, result)
        self.assertTrue(inspect(self.path)["passed"])
        self.assertEqual(counts(self.path), (1, 1))
        code, result = self.cli("resume")
        self.assertEqual(code, 0, result)
        self.assertEqual(counts(self.path), (1, 1))

    def test_conflicting_vendor_is_unchanged(self):
        code, result = self.cli("demo", "--scenario", "conflicting-existing", "--approval", "fixture")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["raw_actor_exit"], 20)
        self.assertEqual(result["reason"], "conflicting_existing")
        self.assertTrue(inspect(self.path)["passed"])
        self.assertEqual(counts(self.path), (1, 0))

    def test_generic_submit_is_blocked_before_portal_receives_it(self):
        create_run(self.path, "happy")
        malicious = PrematureSubmit()
        self.assertEqual(run(self.path, provider=malicious), 30)
        self.assertEqual(counts(self.path), (0, 0))
        with closing(sqlite3.connect(self.path / "workflow.db")) as con:
            reasons = [json.loads(data)["reason"] for (data,) in con.execute("SELECT data FROM events WHERE kind='route_blocked'")]
        self.assertIn("commit_not_armed_or_body_changed", reasons)
        for context in malicious.contexts:
            self.assertEqual(set(context), {"schema_version", "request", "state", "observation", "remaining_steps", "last_result"})
            self.assertNotIn("csrf", json.dumps(context))
            self.assertNotIn("oracle.json", json.dumps(context))

    def test_changed_actual_body_is_blocked_even_with_armed_ticket(self):
        create_run(self.path, "happy")
        self.assertEqual(run(self.path), 10)
        store = Store(self.path)
        try:
            with PortalProcess(self.path / "portal.db") as portal, BrowserController(portal.origin, store) as browser:
                form = browser.page.locator('form[action="/vendors/commit"]')
                original = dict(form.locator("input").evaluate_all("els => els.map(el => [el.name,el.value])"))
                store.data["state"] = "SUBMITTING"
                store.data["commit_attempted"] = True
                store.data["approval"] = {"digest":digest(store.data["review"]), "consumed":True, "expires_at":9999999999}
                store.save("test_trusted_host_arm")
                browser.ticket = {"form":original, "digest":digest(store.data["review"])}
                form.locator('input[name="contact_email"]').evaluate("el => el.value = 'changed@cedar.example'")
                try:
                    form.get_by_role("button", name="Submit vendor", exact=True).click()
                except Exception:
                    pass  # Aborted navigation may raise; assertions use actual server state.
                self.assertTrue(browser.blocked)
            self.assertEqual(counts(self.path), (0, 0))
        finally:
            store.close()

    def test_success_banner_and_actor_claim_do_not_override_database(self):
        code, result = self.cli("demo", "--scenario", "happy", "--approval", "fixture")
        self.assertEqual(code, 0, result)
        self.assertTrue(inspect(self.path)["passed"])
        # The evaluator owns this deliberate corruption; it is not an actor tool.
        with closing(sqlite3.connect(self.path / "portal.db")) as con, con:
            con.execute("DELETE FROM vendors")
        self.assertFalse(inspect(self.path)["passed"])
        actor = json.loads((self.path / "actor-result.json").read_text())
        self.assertEqual(actor["state"], "ACTOR_DONE")
