# U2-B dev02 diagnostic repeat

Main independently audited the first two task pairs. Each policy created the
requested vendor on dev01 and halted on dev02 after five decisions, with zero
approvals, commits or vendor additions on dev02. Both first failures remain
business failures. The original 24-slot development plan still has four
terminal records and twenty pending records; its metrics and evidence are
immutable. A repeat does not increase the distinct task population.

Retained event digests identify the fifth decision as
`fill_from_request(legal_name, c2)`. It follows navigation to `/vendors/new` and
precedes every section-open action. Fixture source places that input inside
initially closed Organisation details. The original collector uses geometry
and style visibility without an explicit closed-details test. Both proposed
fills took about 5.1 seconds before a generic halt, consistent with the clipped
five-second interaction timeout. However, no retained exception type, actual
DOM visibility or actionability snapshot establishes the native failure cause.
Closed-details visibility is a hypothesis, not a verified root cause.

This version therefore adds diagnostics only. `DiagnosticBrowser.interact`
delegates to the original interaction implementation exactly once, returns its
original result, and rethrows its original exception object. The collector,
reference resolver, policy, fixture, gold, scorer, budgets, approval contract
and cleanup remain unchanged. The leased repeat runner explicitly substitutes
that subclass in the original native runner's in-memory browser binding for
the duration of one serial run, then restores it in `finally`. The original
actor source and every earlier seal remain unchanged.

`evaluation-diagnostic.jsonl` records a fixed stage, route path, allowed tool,
request-field identifier, numeric control index, role and fixed exception
category. It does not include exception messages/class names, full URLs,
queries, labels, values, page text, request bodies, cookies or credentials.
On ordinary interaction failure it makes one read-only DOM probe with a
200ms timeout. The probe returns only an allowed tag and boolean geometry,
closed-details and visibility indicators. Failure to probe leaves them
unknown. This is a snapshot after the exception, not proof of DOM state during
the failed wait. Interruption triggers no DOM probe. Logging failure does not
replace the original action result or exception. The journal is capped at 82
records, 128 KiB, and its terminal byte digest is bound to the new receipt.

The new execution identity is `dev02-diagnostic-repeat-01` with source version
`fresh-local-u2b-diagnostics.1`. The plan includes both policies, exact original
dev02 case/dataset hashes, original slot IDs03/04 and original full-plan hash.
All 42 original artifact files and the empty pending directories are pinned.
The plan binds a distinct output directory and requires its reviewed digest
plus the existing explicit main lease before output or runtime construction.
Its exclusive STARTED/terminal records reuse the accepted accounting mechanics.
Repeat reports are separate from the original first-attempt population and
state `new_unique_tasks=0`, original24 slots /4 terminal /20 pending, and
`full_development_complete=false`. No freeze, capability or continuation route
exists here. The original scorer summarizes the one repeated task separately;
its within-repeat denominator is not added to original metrics.

Source/pure controls, using existing dependencies:

```powershell
.venv/Scripts/python.exe -m unittest diagnostic_eval_tests.test_diagnostics -v
.venv/Scripts/python.exe -m diagnostic_eval source-check
```

Future proposed execution, unexecuted and requiring a separate main lease:

```powershell
.venv/Scripts/python.exe -m diagnostic_eval repeat-dev02 --out work/u2b-dev02-diagnostic-repeat-v1 --plan-sha256 <reviewed-repeat-plan-sha256>
.venv/Scripts/python.exe -m diagnostic_eval report --out work/u2b-dev02-diagnostic-repeat-v1
```

Only one failure-focused paired task is proposed: the same exposed dev02
task repeated once per policy, maximum two new attempts and zero new unique
tasks. It can fail again; expected outcomes are unchanged. A diagnostic command
can return zero after terminal business failures, which remain reported as
failures. The original twenty pending tasks require a separate continuation
assignment. Recovery, only after the supervisor declares the prior owner
stopped, does not restart an actor:

```powershell
.venv/Scripts/python.exe -m diagnostic_eval recover --out work/u2b-dev02-diagnostic-repeat-v1 --owner-stopped
```

The worker used two explicitly authorized immutable read-only SQLite
connections to inspect retained state; no application was constructed and no
original file or sidecar changed. Pure tests forbid SQL connections, sockets,
subprocesses and browsers. New native/browser/HTTP/model/account execution,
downloads and publication remain unexecuted. This version fixes observability,
and claims neither a business fix nor a confirmed root cause.
