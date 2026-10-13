# U2-B durable accounting correction

Main's mocked first-invocation `KeyboardInterrupt` probe found that the original
`fresh_eval.native.evaluate` held intentions and results in memory until the
loop ended. This additive coordinator supersedes that orchestration for new
evaluation work. The original package, policies, corpus, auditor, scorer, gates,
manifests and evidence remain byte-for-byte attributable to their prior seal.
The historical full-batch proposal is superseded by the first slice below.

`durable_eval` supports development only and at most two paired tasks. Before
dispatch it saves the complete immutable 12-task, 24-slot plan, including both
policies, every case hash, the dataset hash, old and new source seals, and the
same model configuration and budgets. A reviewed full-plan hash is mandatory
at the native entry point. Endpoint ports are allocated later inside the old
loopback runtime; the frozen configuration binds that allocation rule and
exact runtime source, rather than inventing a port before it exists.
The full plan also binds its one output directory; relocating it or dispatching
the same reviewed hash under another directory is refused.

Each slot has an exclusive `STARTED.json` written, flushed and fsynced before
the actor is called. An exclusive `TERMINAL.json` binds the start bytes, full
plan, source/data/config hashes, returned row and retained raw-file inventory.
The inventory records names, sizes and hashes; it exports neither SQL contents
nor session secrets. The existing independent full-SQL auditor still computes
outcomes and safety inside `fresh_eval.native.run_one`. Accounting does not
replace that auditor or claim its filesystem hashes are a SQL audit.

Receipts have content hashes. A partial start or terminal file remains a spent
attempt. A start without a terminal projects as `interrupted_unknown`; a
never-started slot remains `pending` / `not_attempted`. Caught ordinary failure
is `failed`; `KeyboardInterrupt` and `SystemExit` are interrupted unknown.
Unknown safety, unsafe metrics, latency, usage and charges remain unknown.
Completed receipts whose retained evidence changes project as unknown, with
the original terminal record preserved. The original scorer is used unchanged,
with all 24 intended rows and denominators present. Its aggregate intervention
and tool-count defaults remain its historical semantics; an unknown receipt
does not establish that no intervention or tool call occurred.

`report.json` is an atomic, replaceable projection. It can be rebuilt from the
plan and receipts after report loss. `recover --owner-stopped` records missing
terminals as interrupted unknown only after the caller declares the prior
owner stopped. This declaration is not process-liveness evidence. Recovery
never launches an actor, opens SQL, or restarts a task. Any prior claim, terminal
or historical run directory blocks re-dispatch; there is no retry/resume route.
Fresh output directories are mandatory. Record omissions, duplication and
binding drift fail closed; started rows with missing terminals remain unknown.

This establishes flushed-file accounting under process interruption. It does
not demonstrate a native crash, process termination, Windows power-loss
durability, browser behavior or cleanup. Pure controls inject exceptions and
incomplete records; they guard against sockets, subprocesses, browsers and
SQLite connections and retain their small filesystem artifacts in `work/`.

Source/pure checks, using the existing environment:

```powershell
.venv/Scripts/python.exe -m unittest durable_eval_tests.test_accounting -v
.venv/Scripts/python.exe -m durable_eval source-check
```

Proposed future first slice, unexecuted and requiring a separately assigned
main native/browser lease plus the existing cached-browser environment:

```powershell
.venv/Scripts/python.exe -m durable_eval evaluate-first-slice --out work/u2b-first-slice-accounting-v1 --paired-tasks 2 --phase-seconds 900 --plan-sha256 <reviewed-plan-sha256>
.venv/Scripts/python.exe -m durable_eval report --out work/u2b-first-slice-accounting-v1
```

Main's reviewed complete plan supplies the hash, not an arbitrary new token.
The first two corpus tasks are selected before execution, with both policies
in corpus order. At most four new attempts occur, automatic retries remain
zero, and failure or unsafe/unknown evidence stops later dispatch. Twenty
unexecuted slots stay in the report. A successful bounded command means the
selected slice completed safely; the full development denominator stays
incomplete. `freeze_eligible` and `capability_eligible` are always false here.
No freeze or capability command exists in this coordinator. The original
freeze validator also refuses this partial report. Further development or
capability work requires a new reviewed orchestration and main assignment.

If the supervisor has stopped the old owner after an interrupted future run:

```powershell
.venv/Scripts/python.exe -m durable_eval recover --out work/u2b-first-slice-accounting-v1 --owner-stopped
```

Do not use the legacy in-memory `fresh_eval evaluate` or its historical
72-run proposal for this correction. No native/browser/SQL/process integration,
paid call, account access, package download or publication was exercised by
the worker's source/pure correction.
