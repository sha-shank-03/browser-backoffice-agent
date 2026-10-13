# Collapsed DETAILS collector candidate

Main's13October2026 diagnostic repeat audited two dev02 attempts. Both policies
timed out on `fill_from_request(legal_name,c2)`. The post-exception probe saw an
INPUT within closed DETAILS with client rects present, style visibility not
hidden, and `checkVisibility=false`. The original rect/style-only collector
therefore exposed collapsed content. This supports the specific collector
correction; the snapshot does not reconstruct every instant of the wait or
retroactively add diagnostics to the original first failures.

`fresh-local-u2b-details.1` is an additive candidate. The lineage is:

1. `fresh_eval.browser.EvaluationBrowser`: original collector, selector,
   reference/signature checks, trusted route and approval gates; unchanged.
2. `diagnostic_eval.browser.DiagnosticBrowser`: original interaction wrapper
   and diagnostics version; unchanged.
3. `details_eval.browser.DetailsBrowser`: inherits that wrapper and changes
   only `_controls` to evaluate `details_eval/collector.js` on the same selector.

Before: a control with a client rectangle and non-hidden style was offered,
including the concrete collapsed input main observed. After: the same control
must also be outside collapsed DETAILS content. The collector walks every
ancestor DETAILS. Within a closed ancestor only its first direct SUMMARY and
descendants of that SUMMARY are exempt. An inner SUMMARY remains hidden when
it is ordinary content of a closed outer DETAILS. An open DETAILS does not
hide its content; independently closed nested DETAILS still does. A second
SUMMARY in a closed DETAILS is ordinary hidden content. With no explicit
SUMMARY, no selected content is exempt. Existing rectangle, style and disabled
filters still apply to SUMMARY and its descendants.

Mapping happens before filtering, so each surviving control keeps its original
selector index. The same selector and index serve resolution; neither hidden
fields nor visible controls are renumbered. Roles, labels, values, options,
descriptions, context and required flags are unchanged. No hidden state or new
control metadata is passed to either acting policy. The candidate never writes
`open`, clicks a SUMMARY automatically, injects a selector into model output,
or changes goals, expected outcomes, source request fields or tool authority.
Inherited stale/ambiguity, routing, review and approval checks remain in force.

Both unchanged policies use the same explicitly bound collector in serial
native verification. The native browser-class substitution is restored in
`finally`. Diagnostics retain their original version and post-error limitation.
The semantic-rules policy can explicitly choose the visible SUMMARY when fields
are missing. The historical local double cannot open sections and will hand
off with insufficient evidence on that observation. This policy limitation
remains a quality loss against dev02's unchanged create outcome; it is not
tuned away, recoded as success or hidden by automatically opening sections.

Pure controls execute the exact legacy and candidate JavaScript with authored
DOM doubles. They cover the recorded geometry/style counterexample, flat/open
metadata equality, closed/open nested combinations, first SUMMARY descendants,
second/missing SUMMARY, hidden/disabled controls and stable indices. Python
controls verify collector wiring, stale/ambiguity and route/approval behavior,
both policy decisions, binding restoration, accounting, lineage and cohort
separation. They forbid sockets, subprocesses, browsers and SQLite connections.
These controls do not demonstrate installed-browser behavior or task completion.

Reproducible pure commands with existing dependencies (the JavaScript test
may run in V8 or an already available Node runtime; no browser/install needed):

```powershell
node details_eval_tests/test_collector.js
.venv/Scripts/python.exe -B -m unittest details_eval_tests.test_contract -v
.venv/Scripts/python.exe -B -m details_eval source-check
```

The Python policy controls read the JavaScript result at
`work/details-pure-controls/v8-result.json`. Main can regenerate that result
from the JavaScript command before the Python suite on a fresh checkout:

```powershell
New-Item -ItemType Directory -Force work/details-pure-controls | Out-Null
node details_eval_tests/test_collector.js | Set-Content -Encoding utf8 work/details-pure-controls/v8-result.json
```

The retained original/native evidence is a required read-only input for this
local correction stage. It is not automatically available in a fresh clone.
Source checks refuse missing/changed history rather than fabricate it.

The only native proposal here is one dev02 verification pair, a separate
execution `dev02-details-verification-01`, with at most two new attempts and
zero new unique tasks. It requires main source review, a new explicit lease,
existing cache and the reviewed plan hash. Output is fresh and cannot target
either historical directory or its descendants:

```powershell
.venv/Scripts/python.exe -B -m details_eval verify-dev02 --out work/u2b-dev02-details-verification-v1 --plan-sha256 <reviewed-plan-sha256>
.venv/Scripts/python.exe -B -m details_eval report --out work/u2b-dev02-details-verification-v1
```

Reports explicitly identify changed-source repeats. A zero command exit means
both selected attempts produced terminal known-safe evidence; business losses
remain losses. Main must independently inspect current visible controls and
complete domain state before accepting the native correction. Original
four terminal and twenty pending slots, plus two failed diagnostic repeats,
remain immutable. This CLI exposes no full-development, continuation, freeze
or capability route.

The safe continuation design is a separate corrected-source full-development
cohort with all12 tasks /24 slots pending at the outset. Its twenty slots for
previously unexecuted dev03..12 map to the original pending IDs but have new
execution IDs, source binding and receipts. They can run only after the pair's
independent review, implementation/sealing of full-cohort orchestration,
separate main assignment and bounded named leases (at most two paired tasks
per proposed later lease). The four new-cohort dev01/02 slots are clearly
repeats and require their own gate. Old results and the separate verification
pair are not imported. Thus the candidate verification is not silently reused
as full-cohort evidence. The original twenty pending slots stay pending.

The saved full-cohort JSON is a frozen planning reference to this collector
candidate, not an executable source freeze. Before dispatch main must freeze
the complete future orchestration/configuration, retaining this artifact as
lineage. Unknown/unsafe evidence stops dispatch, started/terminal slots never
replay, and any later code change creates another source cohort. Full source-
specific development proof requires every new-cohort slot and independent
audit; no original12-task success denominator combines old/new source. No
development freeze, capability scoring or live/unseen claim is authorized here.

All prior source manifests, actor/policy/corpus/gold/budgets/approvals and every
original/repeat artifact remain unchanged. The worker ran source/pure only:
no new native/browser/server/application/SQL/Java/HTTP/model/account execution,
download, commit, push or deployment. Native correction and quality acceptance
remain pending independent main review.
