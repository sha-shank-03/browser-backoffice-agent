"""Windows: .venv\\Scripts\\python.exe -m backoffice --help"""
from __future__ import annotations

from argparse import ArgumentParser
import importlib.metadata
import json
from pathlib import Path
import platform
import sqlite3
import sys

from .domain import WorkflowError, digest
from .runner import approve, run
from .store import Store


def doctor():
    if sys.version_info[:2] != (3, 11):
        raise WorkflowError("Use py -3.11 or the documented Python 3.11 venv")
    pins = {"playwright": "1.63.0", "pyee": "13.0.0", "greenlet": "3.3.2", "typing-extensions": "4.15.0"}
    for name, version in pins.items():
        if importlib.metadata.version(name) != version:
            raise WorkflowError(f"Dependency pin mismatch: {name}")
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                browser_version = browser.version
            finally:
                browser.close()
    except Exception as exc:
        raise WorkflowError("Headless shell startup failed. Set PLAYWRIGHT_BROWSERS_PATH and run the documented pinned install: " + str(exc)) from exc
    return {"python": platform.python_version(), "os": platform.platform(), "sqlite": sqlite3.sqlite_version,
            "packages": pins, "browser": browser_version, "mode": "headless_shell", "live_model": "adapter_available_live_unverified"}


def main(argv=None):
    parser = ArgumentParser(description="Fictional local vendor workflow; scripted by default")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    demo = sub.add_parser("demo")
    from evaluation.fixtures import load_suite
    demo.add_argument("--scenario", required=True, choices=tuple(load_suite()["cases"]))
    demo.add_argument("--approval", choices=("manual", "fixture"), default="manual")
    demo.add_argument("--run-dir", required=True, type=Path)
    provider_commands = [demo]
    for command in ("review", "approve", "resume", "cancel"):
        item = sub.add_parser(command)
        item.add_argument("--run-dir", required=True, type=Path)
        if command == "approve":
            item.add_argument("--digest", help="Exact displayed digest; omit for interactive reviewer input")
        if command == "resume":
            provider_commands.append(item)
    for item in provider_commands:
        item.add_argument("--provider", choices=("scripted", "fixed-macro", "ollama"), default="scripted")
        item.add_argument("--allow-live-model", action="store_true")
        item.add_argument("--model", help="Explicit existing local model; never pulled automatically")
        item.add_argument("--endpoint", default="http://127.0.0.1:11434/api/chat")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            print(json.dumps(doctor(), indent=2))
            return 0
        def provider_factory():
            from .providers import FixedMacroProvider, ScriptedProvider
            if args.provider == "ollama":
                from .ollama import OllamaProvider
                return OllamaProvider(args.model, args.endpoint, allow_live=args.allow_live_model)
            return FixedMacroProvider() if args.provider == "fixed-macro" else ScriptedProvider()
        if args.command == "demo":
            from evaluation.fixtures import create_run
            provider_factory()  # Validate opt-in/endpoint before creating any run directory.
            create_run(args.run_dir, args.scenario)
            if args.approval == "fixture":
                from evaluation.harness import execute
                raw_exit = execute(args.run_dir, load_suite()["cases"][args.scenario], provider_factory=provider_factory)[-1]
            else:
                raw_exit = run(args.run_dir, provider_factory())
        elif args.command == "resume":
            if not (args.run_dir / "workflow.db").exists():
                raise WorkflowError("Run does not exist")
            raw_exit = run(args.run_dir, provider_factory())
        elif args.command == "cancel":
            if not (args.run_dir / "workflow.db").exists():
                raise WorkflowError("Run does not exist")
            (args.run_dir / "cancel.request").write_text("operator_cancelled\n", encoding="utf-8")
            print(json.dumps({"cancellation_requested": True, "effect": "next host boundary and final request gate", "rollback_promised": False}))
            return 0
        else:
            if not (args.run_dir / "workflow.db").exists():
                raise WorkflowError("Run does not exist")
            store = Store(args.run_dir)
            try:
                review = store.data["review"]
                if not review:
                    raise WorkflowError("No review is available")
                display = {"review": review, "digest": digest(review), "state": store.data["state"]}
            finally:
                store.close()
            if args.command == "review":
                print(json.dumps(display, indent=2))
                return 0
            if args.digest is None:
                print(json.dumps(display, indent=2))
                supplied = input("Type the complete displayed digest to approve: ").strip()
            else:
                supplied = args.digest
            approve(args.run_dir, supplied)
            print(json.dumps({"state": "APPROVED", "digest": supplied, "approval_kind": "manual_cli"}))
            return 0
        result = json.loads((args.run_dir / "actor-result.json").read_text(encoding="utf-8"))
        result["raw_actor_exit"] = raw_exit
        if raw_exit == 10:
            result["review_artifact"] = "review.json"
            print(json.dumps(result, indent=2))
            return 10
        if raw_exit in {0, 20}:
            from evaluation.verify import write_report
            report = write_report(args.run_dir)
            result["independent_verification"] = report
            print(json.dumps(result, indent=2))
            return 0 if report["passed"] else 1
        print(json.dumps(result, indent=2))
        return raw_exit
    except (WorkflowError, OSError, ValueError, sqlite3.Error, importlib.metadata.PackageNotFoundError) as exc:
        print(json.dumps({"error": str(exc), "passed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
