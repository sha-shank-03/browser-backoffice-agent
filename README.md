# Browser Backoffice Agent

Register a fictional vendor through a local procurement portal, pause for approval of the exact review, and check the final database independently. This implementation uses Python 3.11, Playwright and a **scripted current-observation policy** by default. All executed demonstrations use scripted decisions or local protocol doubles; no live language-model call has been evaluated.

The original contribution is the procurement workflow's authority and evidence contract: approval covers all six vendor values plus draft/session identity; the browser controller checks the actual final form request; a separate verifier checks final records and ordered approval/commit evidence. All requests, portal data and cases are authored fiction.

M1 and M2 received independent local acceptance. The M3 worker batch passed all 50 tests. The frozen thirty-case comparison yielded reactive scripted 30/30 expected outcomes and fixed macro 3/30; all sixty runs were safe. Eighteen separate recovery repeats passed, all 78 retained tasks passed the database/evidence audit, and the verifier rejected all fifteen deliberate corruptions. Thirty definitions, the original 32 code/input hashes and six additive harness hashes remain unchanged. Final independent local acceptance passed on 2026-10-08: a fresh shipping-source copy passed 18 commands, all 50 tests and 1,019 additional checks against 80 saved states (60 comparison, 18 recovery repeats and two quickstart demos). The final check reused installed packages/browser binaries; fresh installation and hosted CI remain unexecuted. These are authored offline integration results, not live-model accuracy.

## Windows quickstart

Run from this repository root on Windows 11+ with Python 3.11. Invoke the venv interpreter directly; activation is unnecessary. The required package wheels and Chromium headless shell need an initial download. No full browser, Java/Maven, Docker, account, API key or model is required.

```powershell
py -3.11 --version
py -3.11 -m venv .venv
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.cache/ms-playwright'
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock
.\.venv\Scripts\python.exe -m playwright install chromium --only-shell
.\.venv\Scripts\python.exe -m backoffice doctor
.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v
.\.venv\Scripts\python.exe -m unittest discover -s tests/contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v
.\.venv\Scripts\python.exe -m backoffice demo --scenario happy --provider scripted --approval fixture --run-dir work/demo-happy
.\.venv\Scripts\python.exe -m evaluation.verify --run-dir work/demo-happy
.\.venv\Scripts\python.exe -m backoffice demo --scenario conflicting-existing --provider scripted --approval fixture --run-dir work/demo-conflict
.\.venv\Scripts\python.exe -m evaluation.verify --run-dir work/demo-conflict
```

For an already installed checkout, reuse its venv/cache and skip installation. Fresh package installation was measured for M1; fresh installation of the final M3 checkout and hosted Linux CI remain unexecuted. Pick unused demo directory names when rerunning the quickstart.

`--approval fixture` is an explicitly simulated reviewer used for reproducible local checks. It verifies the complete candidate against the fictional request outside the provider and records `approval_kind=simulated_fixture`. Manual review is the default.

Use a new run directory; existing evidence is never reset implicitly. Set `PLAYWRIGHT_BROWSERS_PATH` again in each new terminal using the same repository root.

## Manual review and resume

```powershell
.\.venv\Scripts\python.exe -m backoffice demo --scenario happy --provider scripted --approval manual --run-dir work/manual-review
# Exit 10: AWAITING_APPROVAL, with zero vendor rows and zero received commit requests.
.\.venv\Scripts\python.exe -m evaluation.verify --run-dir work/manual-review --expect-awaiting
.\.venv\Scripts\python.exe -m backoffice review --run-dir work/manual-review
.\.venv\Scripts\python.exe -m backoffice approve --run-dir work/manual-review
# Read the complete values and type the displayed SHA-256 digest.
.\.venv\Scripts\python.exe -m backoffice resume --run-dir work/manual-review
.\.venv\Scripts\python.exe -m evaluation.verify --run-dir work/manual-review
.\.venv\Scripts\python.exe -m backoffice resume --run-dir work/manual-review
# Terminal replay starts no browser and creates no duplicate.
```

Automated reviewer tests can supply the same full digest through `approve --digest <displayed-digest>`. The model/provider has no approval tool. Approval expires after 15 minutes. Resume restarts the owned portal with persisted fictional session/draft state and rechecks the review before committing.

`demo` and `resume` print both the actor's raw exit/outcome and an independent verifier report. A conflict is reported as `HANDOFF` with raw actor exit 20; the demo exits 0 only when the expected unchanged outcome is verified. It is never described as successful registration. Exit 10 means approval is pending, 11 means an interruption requiring resume, 30 means cancellation/workflow/budget failure, and 1 means an unexpected failure or failed verification. The separate verifier uses exits 0/1/2 for passed/mismatched/missing-or-corrupt evidence.

`backoffice cancel --run-dir work/manual-review` writes a cancellation request without taking the runner's ownership lock. The host checks it at each boundary and at the final POST gate. Resume persists cancellation if the runner was stopped. Cancellation after a commit attempt reports an unknown write outcome and never promises rollback.

## Development and recovery checks

The ten development cases are `happy`, `conflicting-existing`, `renamed-reordered`, `validation-modal`, `session-expiry`, `exact-existing`, `commit-response-loss`, `pre-review-restart`, `stale-approval` and `unsupported-field`. Use `demo --scenario <name> --approval fixture` for the evaluator's authored fault/reviewer setup. Manual review is demonstrated by `happy`; manual mode does not inject evaluator restart barriers.

```powershell
.\.venv\Scripts\python.exe -m evaluation.run --suite development --agents reactive-scripted,fixed-macro --out work/m2-eval
.\.venv\Scripts\python.exe -m evaluation.check_report --report work/m2-eval/report.json --require-cases 10 --require-safe
.\.venv\Scripts\python.exe -m evaluation.freeze --suite heldout --check
```

The fixed macro uses canonical labels and one documented happy-path order, the same host tools/approval/request gate, and the same requests, reviewer decisions and verifier. It must pass the canonical control. Every baseline failure remains in the denominator; acceptance requires correct reactive outcomes and safety for both approaches, with no required performance gap.

After a persisted commit intent, approval is consumed even if no response or request can be established. A new runner searches the portal by registration reference, opens the matching detail page and checks all six displayed values. It can finish an exact record or hand off a conflict/uncertainty; it cannot create another draft or submit again. A fresh review reload checks session, draft revision and all values before consuming approval. The fixture makes vendor creation and its audit atomic and enforces unique references; these are portal guarantees.

Recovery tests exercise an orderly interruption and recreated runner/portal/browser, plus deliberate response loss after the portal transaction. Abrupt OS kill and power loss are untested and may leave the exclusive `run.lock`, stale cookie export or owned process requiring operator inspection. The lock is not automatically stolen. This demonstration does not claim general crash durability.

## Frozen final evaluation

The original thirty cases and actor/evaluator freeze stay intact. Additive M3 harness utilities in `acceptance/` have their own checkpoint; this avoids changing the frozen evaluation loop merely to add repeats. The repeat command is `acceptance.stress`, replacing the plan's proposed `evaluation.run --suite recovery-repeat` spelling while preserving the exact six-case-times-three contract.

The following commands executed successfully in the authorized M3 worker batch on 2026-10-08. The explicit opt-in flag is required for held-out execution. Use a new output directory for every comparison/repeat; preserve failures and do not tune the policy or relabel cases after scoring. Exact command results and resource measurements are in [EVIDENCE.md](EVIDENCE.md).

```powershell
.\.venv\Scripts\python.exe -m evaluation.freeze --suite heldout --check
.\.venv\Scripts\python.exe -m acceptance.checkpoint --check
.\.venv\Scripts\python.exe -m unittest discover -s acceptance/tests -v
.\.venv\Scripts\python.exe -m evaluation.run --suite heldout --allow-heldout --agents reactive-scripted,fixed-macro --out work/m3-heldout
.\.venv\Scripts\python.exe -m evaluation.check_report --report work/m3-heldout/report.json --require-cases 30 --require-safe
.\.venv\Scripts\python.exe -m acceptance.stress --allow-heldout --out work/m3-repeat
.\.venv\Scripts\python.exe -m acceptance.stress --check --out work/m3-repeat
.\.venv\Scripts\python.exe -m acceptance.audit --heldout-out work/m3-heldout --stress-out work/m3-repeat
.\.venv\Scripts\python.exe -m acceptance.sensitivity --source-run work/m3-heldout/reactive-scripted/heldout-01 --out work/m3-verifier-negative
```

The comparison has sixty runs: thirty per approach. Report creation completion out of nineteen, exact-existing handling out of two, unchanged handoffs out of nine, each family, all failures and safety independently. The predefined subset `heldout-13,15,17,22,24,30` runs in that fixed order for each of three repetitions: eighteen additional reactive runs, six distinct cases. Repeat results are never added to the thirty-case denominator. Fifteen deliberate verifier corruptions operate on isolated copies of an accepted positive run; the original evidence remains intact. Pure tests use synthetic metadata and a manually constructed development SQLite control, not scored held-out runs.

The worker batch met the target: reactive 30/30 expected postconditions (19/19 creation, 2/2 existing, 9/9 unchanged handoff), safety for all comparison/repeat runs, auditable retained task evidence, and all fifteen corruptions rejected. The macro achieved 3/30 (0/19 creation, 2/2 existing, 1/9 handoff); all 27 failures are retained. Repeats are 18/18 and stay outside the thirty-case denominator. There is no minimum baseline uplift and no model-accuracy claim. A held-out failure must remain in evidence; a later fix needs an explicitly versioned evaluation decision.

## Supported labels and provider transport

The reactive policy's published vocabulary is bounded. Reordering these fields is supported; unknown or ambiguous required controls cause handoff.

| Field | Supported accessible labels |
| --- | --- |
| Legal name | Legal name; Vendor legal name; Registered business name |
| Registration reference | Registration reference; Vendor reference; Business reference |
| Country | Country; Operating country; Country code |
| Contact email | Contact email; Vendor email; Order contact email |
| Category | Category; Vendor category; Procurement category |
| Payment terms | Payment terms; Invoice terms; Settlement terms |

The stdlib Ollama adapter targets literal loopback HTTP `/api/chat`, sends non-streaming tools, and returns assistant tool calls and prior tool results. It requires `--provider ollama --allow-live-model --model <existing-local-model>`, optionally `--endpoint http://127.0.0.1:11434/api/chat`. It never installs a runtime, pulls weights, uses an environment proxy, follows redirects, or chooses a fallback. Local HTTP doubles verify this protocol; runtime/model identity, digest/license and live accuracy remain unverified. Any future authorized live evaluation must record those identities and separate its results from offline scores.

Host bounds are 40 decisions across resumes, 120 active offline seconds (300 for live), one protocol correction, one reauthentication, three unchanged cycles, two precommit read retries with 0.25/0.5-second backoff, and one final dispatch per approval. Observations/responses/context are bounded to 24/16/64 KiB; generation is configured to 512 tokens/call with an 8,192 reported-token run cap. Missing usage is recorded as unavailable. Evidence is capped at 20 MiB with a shutdown reserve; browser action/navigation timeouts are 5/10 seconds, and provider calls have a total deadline of at most 30 seconds.

## How it works

The actor sees an immutable request and each newly observed page's accessible text, visible controls and displayed records. It proposes one typed action. Tools copy values from the request, choose an observed option, click a visible control, request review or submit an approved review. Unknown tools, invented values, stale references and unsupported completion claims fail closed. No shell, database, filesystem, arbitrary JavaScript, HTTP-client or unrestricted URL tool is exposed.

The portal runs in a separate owned process. Its HTML forms persist drafts and uniquely keyed vendors in SQLite. The trusted controller routes requests to that exact loopback origin and blocks the final POST unless the host has consumed a matching approval and armed one exact form body. The same boundary blocks a generic final click and a changed body before the portal receives either request.

After the actor stops, `evaluation.verify` opens the portal and workflow databases read-only. It independently checks exact vendor values, count/uniqueness, unchanged prior rows, portal audit, and approval-before-intent-before-dispatch ordering. It does not import actor normalization or completion functions. A success banner and actor claim cannot override missing or wrong records.

Run evidence under `work/` includes `workflow.db`, `portal.db`, `events.jsonl`, `review.json`, `actor-result.json` and `verification.json`. `browser-state.json` contains only a fictional local session and is ignored along with all run data. Review the actual commands and unexecuted checks in [EVIDENCE.md](EVIDENCE.md).

Component/state diagrams, persistence details, the recovery boundary and design choices are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Boundaries and limitations

- This authored accessible portal uses a published label vocabulary and a stable review schema. It does not demonstrate resilience to arbitrary legacy UI changes.
- Scripted decisions and local protocol doubles demonstrate selected integration/protocol behavior, not language-model accuracy. The live adapter remains unexecuted.
- One commit is attempted per approval; portal uniqueness supplies a separate fixture guarantee. Uncertain outcomes use visible UI reconciliation without resubmission. This does not promise exactly-once behavior on other sites.
- Tested restarts are orderly, not abrupt OS termination or power loss. Stale lock/process inspection is manual; automatic stale-lock recovery is excluded.
- Tool authority is enforced outside provider output, but local processes share filesystem privileges. This is not hostile-code isolation or enterprise authentication. Direct manual access to the fictional portal is outside the agent controller's approval gate.
- The stdlib HTTP server is localhost-only demonstration infrastructure, unsuitable for production. The network boundary covers application requests, not all browser background networking.
- The small authored held-out suite uses new values and combinations of known vocabulary; its author knows the families. Its observed scripted completion rates do not establish live-model accuracy, arbitrary-site generalization, production adoption or employer endorsement.

## Linux / free CI

Use an explicitly selected Python 3.11 interpreter to create `.venv`, then `.venv/bin/python` for all commands. Linux equivalents are:

```bash
python3.11 -m venv .venv
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
.venv/bin/python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock
.venv/bin/python -m playwright install --with-deps chromium --only-shell
.venv/bin/python -m backoffice doctor
.venv/bin/python -m unittest discover -s tests/unit -v
.venv/bin/python -m unittest discover -s tests/contract -v
.venv/bin/python -m unittest discover -s tests/integration -v
.venv/bin/python -m unittest discover -s acceptance/tests -v
.venv/bin/python -m acceptance.checkpoint --check
.venv/bin/python -m evaluation.run --suite heldout --allow-heldout --agents reactive-scripted,fixed-macro --out work/ci-heldout
.venv/bin/python -m evaluation.check_report --report work/ci-heldout/report.json --require-cases 30 --require-safe
```

The prepared workflow uses immutable checkout/setup-python action SHAs, read-only repository permissions, no secrets, no model calls and no stored artifact uploads. It includes the fifteen verifier corruptions; eighteen recovery repeats remain an explicit final local acceptance command, rather than every-PR work. Remote CI has not been run. Standard hosted compute is free for public repositories; private quotas and stored artifacts have separate limits. CI reruns this public fixture suite and is not a newly unseen held-out benchmark.

Source/data attribution and dependency licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Project code and authored fixtures use the MIT license.
