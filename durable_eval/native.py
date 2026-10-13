"""Future first-slice wrapper. No real runtime is imported before the old lease."""
from fresh_eval.lease import require_lease
from .ledger import ROOT, create_plan, execute_first_slice, make_plan, scoped_path


def evaluate_first_slice(out, binding, *, expected_plan_sha256=None, paired_tasks=2, phase_seconds=900):
    require_lease()
    from .source_check import binding as current_binding
    if binding != current_binding():
        raise ValueError("native_current_source_binding_required")
    relative = scoped_path(out).relative_to(ROOT).as_posix()
    if make_plan(binding, paired_tasks=paired_tasks, phase_seconds=phase_seconds,
                 output_relative=relative)["plan_sha256"] != expected_plan_sha256:
        raise ValueError("reviewed_full_plan_hash_required")
    ledger = create_plan(out, binding, paired_tasks=paired_tasks, phase_seconds=phase_seconds)
    runtime_binding = {**binding, "evaluation_plan_sha256": ledger.plan["plan_sha256"],
                       "evaluation_configuration_sha256": ledger.plan["slots"][0]["configuration_sha256"]}

    def executor(case, agent, row, deadline):
        from fresh_eval.native import run_one
        return run_one(case, agent, row, runtime_binding, ledger.manifest, deadline)

    return execute_first_slice(ledger, executor)
