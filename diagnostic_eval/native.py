"""Future leased diagnostic repeat; delegates the original run_one unchanged."""
from contextlib import contextmanager
from durable_eval.ledger import ROOT, execute_first_slice, scoped_path
from fresh_eval.lease import require_lease
from .repeat import create, make_plan
from . import VERSION


@contextmanager
def bind_browser():
    # Serial, explicit runtime substitution, restored even on interruption.
    from fresh_eval import native
    from fresh_eval.browser import EvaluationBrowser
    from .browser import DiagnosticBrowser
    if native.EvaluationBrowser is not EvaluationBrowser:
        raise ValueError("unexpected_runtime_browser_binding")
    native.EvaluationBrowser = DiagnosticBrowser
    try: yield
    finally: native.EvaluationBrowser = EvaluationBrowser


def evaluate(out, binding, expected_plan_sha256):
    require_lease()
    from .source_check import binding as current_binding
    if binding != current_binding(): raise ValueError("current_diagnostic_source_binding_required")
    relative = scoped_path(out).relative_to(ROOT).as_posix()
    if make_plan(binding, output_relative=relative)["plan_sha256"] != expected_plan_sha256:
        raise ValueError("reviewed_repeat_plan_hash_required")
    ledger = create(out, binding)
    runtime_binding = {**binding, "evaluation_plan_sha256": ledger.plan["plan_sha256"],
                       "evaluation_configuration_sha256": ledger.plan["slots"][0]["configuration_sha256"],
                       "diagnostic_version": VERSION, "execution_id": ledger.plan["execution_id"],
                       "attempt_kind": "repeat_of_same_exposed_task", "original_plan_sha256": ledger.plan["original_plan_sha256"]}
    def executor(case, agent, row, deadline):
        from fresh_eval.native import run_one
        with bind_browser():
            return run_one(case, agent, row, runtime_binding, ledger.full_manifest, deadline)
    return execute_first_slice(ledger, executor)
