"""Explicit U2-B commands. Native evaluation is guarded; no live/sandbox mode."""
from argparse import ArgumentParser
import json
from pathlib import Path

from .cases import load,sha,BUDGETS
from .freeze import validate_development,check_freeze
from .reporting import AGENTS,summarize
from .source_check import ROOT,check,binding


def audit_report(report):
    from .auditor import inspect,read_run
    manifest=load(report["suite"])
    current=binding()
    if report["source_binding"]!=current or report["dataset_sha256"]!=sha(manifest):raise ValueError("report_source_drift")
    indexed={c["id"]:c for c in manifest["cases"]}
    rows=[]
    for old in report["rows"]:
        row=dict(old)
        if row["attempted"]:
            run=Path(row["run_dir"]).resolve()
            if not run.is_relative_to((ROOT/"work").resolve()):raise ValueError("scoped_evaluation_evidence_required")
            saved=json.loads((run/"evaluation-oracle.json").read_text(encoding="utf-8"))
            case=indexed[row["case_id"]]
            expected_binding={**current,"case_sha256":sha(case),"dataset_sha256":sha(manifest),"agent":row["agent"],"budgets":BUDGETS}
            oracle=saved["oracle"]
            if oracle["request"]!=case["request"] or oracle["expected"]!=case["expected"] or oracle["evaluation_binding"]!=expected_binding:
                raise ValueError("case_oracle_drift")
            row["verification"]=inspect(read_run(run,oracle,saved["before"]))
        rows.append(row)
    return summarize(manifest,rows)


def work_path(raw):
    path=Path(raw).resolve()
    if not path.is_relative_to((ROOT/"work").resolve()):raise ValueError("repository_work_output_required")
    return path


def require_native_freeze_proof(frozen,current):
    """A count/hash-shaped JSON token alone cannot authorize capability scoring."""
    check_freeze(frozen,current)
    path=work_path(frozen["development_report_path"])
    report=json.loads(path.read_text(encoding="utf-8"))
    if sha(report)!=frozen["development_report_sha256"]:raise ValueError("development_receipt_changed")
    validate_development(report,current)
    checked=audit_report(report)
    baseline=checked["agents"]["semantic-rules-v2"]
    if not checked["complete"] or baseline["expected_postconditions"]["n"]!=12 or baseline["safe"]["n"]!=12:
        raise ValueError("native_development_sql_proof_required")
    return True


def main(argv=None):
    parser=ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("source-check")
    evaluate=commands.add_parser("evaluate")
    evaluate.add_argument("--suite",choices=("development-v2","capability-v2"),required=True)
    evaluate.add_argument("--out",required=True)
    evaluate.add_argument("--freeze",type=Path)
    evaluate.add_argument("--phase-seconds",type=int,choices=(900,1800),required=True)
    freeze=commands.add_parser("freeze")
    freeze.add_argument("--development-report",type=Path,required=True)
    freeze.add_argument("--out",required=True)
    audit=commands.add_parser("audit")
    audit.add_argument("--report",type=Path,required=True)
    audit.add_argument("--require-cases",type=int,choices=(12,24),required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="source-check":
            result=check();print(json.dumps(result,indent=2));return 0 if result["passed"] else 1
        if args.command=="evaluate":
            from .lease import require_lease
            require_lease() # Before native import, socket, SQL or browser creation.
            from .native import evaluate as execute
            frozen=json.loads(args.freeze.read_text()) if args.freeze else None
            result=execute(args.suite,work_path(args.out),binding(),frozen=frozen,phase_seconds=args.phase_seconds)
            print(json.dumps(result["summary"],indent=2))
            return 0 if result["summary"]["complete"] and all(a["safe"]["n"]==result["summary"]["intended_unique_tasks"] for a in result["summary"]["agents"].values()) else 1
        report=json.loads(args.development_report.read_text() if args.command=="freeze" else args.report.read_text())
        independently_checked=audit_report(report)
        if args.command=="freeze":
            from .lease import require_lease
            require_lease()
            if not independently_checked["complete"]:raise ValueError("development_incomplete")
            frozen=validate_development(report,binding())
            frozen["development_report_path"]=str(work_path(args.development_report))
            # Re-read SQL checks, not only a stored summary or actor outcome.
            baseline=independently_checked["agents"]["semantic-rules-v2"]
            if baseline["expected_postconditions"]["n"]!=12 or baseline["safe"]["n"]!=12:raise ValueError("native_development_controls_failed")
            target=work_path(args.out)
            if target.exists():raise ValueError("freeze_already_exists")
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(frozen,indent=2)+"\n",encoding="utf-8")
            print(json.dumps(frozen,indent=2));return 0
        print(json.dumps(independently_checked,indent=2))
        return 0 if independently_checked["complete"] and independently_checked["intended_unique_tasks"]==args.require_cases and all(a["safe"]["n"]==args.require_cases for a in independently_checked["agents"].values()) else 1
    except Exception:
        print(json.dumps({"passed":False,"code":"invalid_or_unauthorized_u2b_command","live_model":False,"external_site_verified":False}))
        return 1


if __name__=="__main__":raise SystemExit(main())
