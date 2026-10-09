"""Corrupt isolated evaluator-owned copies; the original actor evidence stays intact."""
from argparse import ArgumentParser
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3

from evaluation.verify import inspect

VARIANTS = ("missing_vendor", "wrong_field", "extra_vendor", "duplicate_reference", "wrong_actor_outcome",
            "unconsumed_approval", "wrong_approval_digest", "changed_review_values", "expired_approval",
            "missing_dispatch", "late_grant", "duplicate_received_commit", "wrong_created_values",
            "wrong_draft_identity", "wrong_revision")


def corrupt(directory, variant):
    if variant not in VARIANTS:
        raise ValueError("Unknown deliberate verifier corruption")
    with closing(sqlite3.connect(directory / "workflow.db")) as workflow, workflow:
        data = json.loads(workflow.execute("SELECT data FROM run WHERE id=1").fetchone()[0])
        if variant == "wrong_actor_outcome":
            data["outcome"] = "existing"
        elif variant == "unconsumed_approval":
            data["approval"]["consumed"] = False
        elif variant == "wrong_approval_digest":
            data["approval"]["digest"] = "0" * 64
        elif variant == "changed_review_values":
            data["review"]["values"]["contact_email"] = "wrong@corruption.example"
        elif variant == "expired_approval":
            data["approval"]["expires_at"] = 0
        elif variant == "missing_dispatch":
            workflow.execute("DELETE FROM events WHERE kind='commit_dispatched'")
        elif variant == "late_grant":
            workflow.execute("UPDATE events SET seq=(SELECT MAX(seq)+1 FROM events) WHERE kind='approval_granted'")
        workflow.execute("UPDATE run SET data=? WHERE id=1", (json.dumps(data),))
    with closing(sqlite3.connect(directory / "portal.db")) as portal, portal:
        if variant == "missing_vendor":
            portal.execute("DELETE FROM vendors")
        elif variant == "wrong_field":
            portal.execute("UPDATE vendors SET contact_email='wrong@corruption.example'")
        elif variant == "extra_vendor":
            portal.execute("INSERT INTO vendors(legal_name,registration_ref,country,contact_email,category,payment_terms) SELECT legal_name,'DEMO-V-EXTRA',country,contact_email,category,payment_terms FROM vendors LIMIT 1")
        elif variant == "duplicate_reference":
            # Deliberate evaluator corruption tests detection even if schema uniqueness is lost.
            portal.execute("ALTER TABLE vendors RENAME TO vendors_original")
            portal.execute("CREATE TABLE vendors AS SELECT * FROM vendors_original")
            portal.execute("DROP TABLE vendors_original")
            portal.execute("INSERT INTO vendors SELECT * FROM vendors")
        elif variant == "duplicate_received_commit":
            rows = portal.execute("SELECT at,kind,data FROM audit WHERE kind='http_post'").fetchall()
            row = next(row for row in rows if json.loads(row[2]).get("path") == "/vendors/commit")
            portal.execute("INSERT INTO audit(at,kind,data) VALUES(?,?,?)", row)
        elif variant in {"wrong_created_values", "wrong_draft_identity", "wrong_revision"}:
            seq, raw = portal.execute("SELECT seq,data FROM audit WHERE kind='vendor_created'").fetchone()
            event = json.loads(raw)
            if variant == "wrong_created_values":
                event["values"]["contact_email"] = "wrong@corruption.example"
            elif variant == "wrong_draft_identity":
                event["draft_id"] = "wrong-draft"
            else:
                event["revision"] += 1
            portal.execute("UPDATE audit SET data=? WHERE seq=?", (json.dumps(event), seq))


def evaluate(source, output):
    positive = inspect(source)
    if not positive["passed"] or positive["vendor_creations"] != 1:
        raise ValueError("Positive sensitivity control must be one independently verified creation")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Sensitivity output must be new; preserve earlier corrupt copies")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for variant in VARIANTS:
        directory = output / variant
        directory.mkdir()
        for filename in ("workflow.db", "portal.db", "oracle.json"):
            shutil.copy2(source / filename, directory / filename)
        corrupt(directory, variant)
        result = inspect(directory)
        results.append({"variant": variant, "rejected": result["passed"] is False, "inspection": result})
    report = {"schema_version": 1, "kind": "verifier_sensitivity", "positive_control_passed": True,
              "variants": len(VARIANTS), "rejected": sum(result["rejected"] for result in results),
              "passed": all(result["rejected"] for result in results), "results": results}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.source_run, args.out)
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
