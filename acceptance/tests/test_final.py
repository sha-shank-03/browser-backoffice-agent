"""Pure source-stage checks: synthetic metadata/SQLite only, no actor/browser/HTTP."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from acceptance.audit import identities, inspect_tasks
from acceptance import checkpoint
from acceptance.sensitivity import VARIANTS, evaluate
from acceptance.stress import expected_pairs, inspect as inspect_stress
from acceptance.stress import main as stress_main
from evaluation.verify import inspect

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ("legal_name", "registration_ref", "country", "contact_email", "category", "payment_terms")
MANIFEST = json.loads((ROOT / "evaluation/heldout.json").read_text())
REQUEST = json.loads((ROOT / "fixtures/requests/cedar.json").read_text())


def hash_value(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def positive_fixture(directory):
    directory.mkdir()
    review = {"schema_version": 1, "task_id": "synthetic-unit", "request_hash": hash_value(REQUEST), "action": "create_vendor",
              "draft_id": "unit-draft", "revision": 1, "session_id": "unit-session", "values": REQUEST}
    signature = hash_value(review)
    data = {"state": "ACTOR_DONE", "outcome": "created", "reason": None, "provider": "scripted:reactive-ui-v2", "steps": 14,
            "active_seconds": 0.5, "review": review, "reauth_attempts": 0,
            "approval": {"digest": signature, "consumed": True, "expires_at": 100}}
    with closing(sqlite3.connect(directory / "workflow.db")) as con, con:
        con.execute("CREATE TABLE run(id INTEGER PRIMARY KEY,data TEXT)")
        con.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,at REAL,kind TEXT,data TEXT)")
        con.execute("INSERT INTO run VALUES(1,?)", (json.dumps(data),))
        for seq, kind in enumerate(("approval_granted", "commit_intent", "commit_dispatched"), 1):
            payload = {"digest" if seq == 1 else "approval_digest": signature}
            con.execute("INSERT INTO events VALUES(?,?,?,?)", (seq, seq, kind, json.dumps(payload)))
    with closing(sqlite3.connect(directory / "portal.db")) as con, con:
        con.execute("CREATE TABLE vendors(id INTEGER PRIMARY KEY, legal_name TEXT, registration_ref TEXT UNIQUE, country TEXT, contact_email TEXT, category TEXT, payment_terms TEXT)")
        con.execute("CREATE TABLE audit(seq INTEGER PRIMARY KEY,at REAL,kind TEXT,data TEXT)")
        con.execute("INSERT INTO vendors VALUES(1,?,?,?,?,?,?)", tuple(REQUEST[field] for field in FIELDS))
        con.execute("INSERT INTO audit VALUES(1,3,'http_post',?)", (json.dumps({"path": "/vendors/commit"}),))
        con.execute("INSERT INTO audit VALUES(2,4,'vendor_created',?)", (json.dumps({"values": REQUEST, "draft_id": "unit-draft", "revision": 1}),))
    oracle = {"schema_version": 1, "scenario": "synthetic-development-positive", "request": REQUEST, "before": [], "expected": [REQUEST], "outcome": "created"}
    (directory / "oracle.json").write_text(json.dumps(oracle))


def stress_report():
    return {"kind": "stress_recovery", "complete": True, "case_count": 6, "repeat_count": 3, "agents": ["reactive-scripted"],
            "suite": "heldout", "version": MANIFEST["version"], "seed": MANIFEST["seed"], "mode": "scripted_offline_no_live_model",
            "results": [{"repeat": repeat, "case": case, "passed": True, "safe": True} for repeat, case in expected_pairs(MANIFEST)]}


def comparison_report():
    return {"complete": True, "suite": "heldout", "version": MANIFEST["version"], "seed": MANIFEST["seed"],
            "mode": "scripted_offline_no_live_model", "case_count": 30, "agents": ["reactive-scripted", "fixed-macro"],
            "results": [{"agent": agent, "case": case} for agent in ("reactive-scripted", "fixed-macro") for case in MANIFEST["case_order"]]}


class FinalPureTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "work", prefix="m3-pure-")
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_repeat_denominator_is_six_times_three_without_new_distinct_cases(self):
        report = stress_report()
        result = inspect_stress(report, MANIFEST)
        self.assertTrue(result["passed"])
        self.assertEqual(len(report["results"]), 18)
        self.assertEqual(len({row["case"] for row in report["results"]}), 6)
        self.assertEqual(result["repeats"], {str(n): {"passed": 6, "denominator": 6} for n in range(1, 4)})

    def test_missing_duplicate_out_of_order_and_unsafe_repeats_fail(self):
        variants = []
        missing = stress_report()
        missing["results"].pop()
        variants.append(missing)
        duplicate = stress_report()
        duplicate["results"][-1] = deepcopy(duplicate["results"][0])
        variants.append(duplicate)
        out_of_order = stress_report()
        out_of_order["results"].reverse()
        variants.append(out_of_order)
        unsafe = stress_report()
        unsafe["results"][0]["safe"] = False
        variants.append(unsafe)
        for report in variants:
            with self.subTest():
                self.assertFalse(inspect_stress(report, MANIFEST)["passed"])

    def test_comparison_metadata_requires_both_full_ordered_denominators(self):
        report = comparison_report()
        self.assertTrue(identities(report, MANIFEST))
        report["results"].pop()
        self.assertFalse(identities(report, MANIFEST))
        report = comparison_report()
        report["results"][0], report["results"][1] = report["results"][1], report["results"][0]
        self.assertFalse(identities(report, MANIFEST))

    def test_synthetic_success_claims_cannot_replace_absent_databases(self):
        report = comparison_report()
        for row in report["results"]:
            row.update(passed=True, safe=True)
        (self.directory / "report.json").write_text(json.dumps(report))
        result = inspect_tasks(self.directory, MANIFEST)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["tasks"]), 60)
        self.assertTrue(all(task["checks"]["complete_readable_evidence"] is False for task in result["tasks"]))

    def test_verifier_positive_control_and_fifteen_corruptions_are_distinct(self):
        source = self.directory / "source"
        positive_fixture(source)
        self.assertTrue(inspect(source)["passed"])
        before = {path.name: path.read_bytes() for path in source.iterdir()}
        report = evaluate(source, self.directory / "negative")
        self.assertTrue(report["passed"])
        self.assertEqual(report["rejected"], 15)
        self.assertEqual({row["variant"] for row in report["results"]}, set(VARIANTS))
        self.assertEqual(before, {path.name: path.read_bytes() for path in source.iterdir()})

    def test_sensitivity_refuses_to_overwrite_failed_evidence(self):
        source = self.directory / "source"
        positive_fixture(source)
        target = self.directory / "existing"
        target.mkdir()
        (target / "report.json").write_text("preserve")
        with self.assertRaises(ValueError):
            evaluate(source, target)
        self.assertEqual((target / "report.json").read_text(), "preserve")

    def test_stress_cannot_start_without_opt_in_or_create_output(self):
        target = self.directory / "not-created"
        with patch("sys.argv", ["stress", "--out", str(target)]), self.assertRaises(SystemExit):
            stress_main()
        self.assertFalse(target.exists())

    def test_additive_checkpoint_normalizes_line_endings_and_detects_source_change(self):
        package = self.directory / "acceptance"
        package.mkdir()
        source = package / "example.py"
        source.write_bytes(b"one\ntwo\n")
        signature = checkpoint.file_hash(source)
        source.write_bytes(b"one\r\ntwo\r\n")
        self.assertEqual(checkpoint.file_hash(source), signature)
        evaluation = self.directory / "evaluation"
        evaluation.mkdir()
        original = evaluation / "heldout-freeze.json"
        original.write_text("{}\n")
        with patch.object(checkpoint, "ROOT", self.directory), patch.object(checkpoint, "MANIFEST", package / "checkpoint.json"), patch.object(checkpoint, "original_check", return_value={"passed": True}):
            manifest = {"files": checkpoint.snapshot(), "original_freeze_sha256": checkpoint.file_hash(original)}
            checkpoint.MANIFEST.write_text(json.dumps(manifest))
            self.assertTrue(checkpoint.check()["passed"])
            source.write_text("changed\n")
            self.assertFalse(checkpoint.check()["passed"])
            self.assertEqual(checkpoint.check()["changed_additive_files"], ["acceptance/example.py"])
