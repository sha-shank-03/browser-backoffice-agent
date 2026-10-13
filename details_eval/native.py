"""Future guarded same-collector verification for both unchanged policies."""
from contextlib import contextmanager
from durable_eval.ledger import ROOT, execute_first_slice, scoped_path
from fresh_eval.lease import require_lease
from .repeat import create, make_plan
from . import VERSION


@contextmanager
def bind_collector():
    from fresh_eval import native
    from fresh_eval.browser import EvaluationBrowser
    from .browser import DetailsBrowser
    if native.EvaluationBrowser is not EvaluationBrowser: raise ValueError("unexpected_runtime_browser_binding")
    native.EvaluationBrowser = DetailsBrowser
    try: yield
    finally: native.EvaluationBrowser = EvaluationBrowser


def evaluate(out, binding, expected_plan_sha256):
    require_lease()
    from .source_check import binding as current_binding
    if binding != current_binding(): raise ValueError("current_details_source_binding_required")
    relative = scoped_path(out).relative_to(ROOT).as_posix()
    if make_plan(binding, output_relative=relative)["plan_sha256"] != expected_plan_sha256:
        raise ValueError("reviewed_details_verification_plan_required")
    ledger = create(out, binding)
    runtime_binding = {**binding, "evaluation_plan_sha256": ledger.plan["plan_sha256"],
                       "evaluation_configuration_sha256": ledger.plan["slots"][0]["configuration_sha256"],
                       "collector_version": VERSION, "execution_id": ledger.plan["execution_id"],
                       "attempt_kind": "changed_collector_repeat_of_same_exposed_task", "original_plan_sha256": ledger.plan["original_plan_sha256"]}
    def executor(case, agent, row, deadline):
        from fresh_eval.native import run_one
        with bind_collector(): return run_one(case, agent, row, runtime_binding, ledger.full_manifest, deadline)
    return execute_first_slice(ledger, executor)
