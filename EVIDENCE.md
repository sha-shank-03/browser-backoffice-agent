# Evidence

Decisions are scripted or explicitly adversarial local test doubles. No live model, credentials, model weights, external account action, remote CI run, publication or deployment has occurred. M1 and M2 received independent local acceptance on 2026-10-08. M2's independent reviewer reran six commands, 42 tests and twenty fresh development tasks, then added 92 direct database/authority checks. M3 source acceptance included four independently run commands, nineteen pure tests and 104 additional conditions. The M3 worker runtime batch below passed all nineteen commands; final independent runtime acceptance remains pending.

## M1 commands executed

Commands ran from the repository root on Windows; `py -3.11` selected Python 3.11.9. No ambiguous unqualified Python invocation was used during implementation.

| Command | Exit | Observed result |
| --- | ---: | --- |
| `py -3.11 --version` | 0 | Python 3.11.9 |
| `py -3.11 -m unittest discover -s tests/unit -v` | 0 | 6/6 passed; request validation, exact review digest, approval, owner lock, false success rejection and read-only verifier |
| `py -3.11 -m unittest discover -s tests/contract -v` | 0 | 4/4 passed; malformed/multiple/unknown calls, stale refs and observation-driven scripted decisions |
| Initial PowerShell lease guard using `ConvertFrom-Json` and reparsing `[DateTimeOffset]::Parse(...)` | 1 | Incorrectly reported expiry after PowerShell date conversion; stopped before metadata/dependency/browser transfer. Corrected by parsing raw ISO timestamps in Python. |
| Corrected Python 3.11 lease guard, official PyPI hash metadata selection, `py -3.11 -m venv .venv` | 0 | Active lease confirmed; exact lock written from versioned metadata; Python 3.11 venv created |

| `.\.venv\Scripts\python.exe -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock` | 0 | Four exact packages installed; wheel hashes enforced; no pip upgrade performed |
| `.\.venv\Scripts\python.exe -m playwright install chromium --only-shell` | 0 | Headless shell 153.0.8010.12, revision 1243; installer-required FFmpeg 1011 and Winldd 1007; no full browser or other engine |
| `.\.venv\Scripts\python.exe -m backoffice doctor` | 0 | Python/package pins and native browser startup passed; SQLite 3.45.1 |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v` (first run) | 1 | 0/5 passed, 5 failures in 12.254 seconds. Form clicks returned before navigation; next observation saw a destroyed execution context. No unauthorized vendor write occurred. Added an explicit registered-before-click DOM-content navigation wait. Assertions and cases unchanged. |

| `.\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v` (second run) | 1 | 0/5 passed, 5 failures in 10.687 seconds. Explicit navigation waits exposed `net::ERR_EMPTY_RESPONSE`: the handler's inherited `connection` socket shadowed a database helper. Renamed helper to `database_connection` and retained portal stderr per run. Assertions unchanged. |

| `.\.venv\Scripts\python.exe -m backoffice demo --scenario happy --provider scripted --approval fixture --run-dir work/demo-happy` | 0 | 14 scripted decisions; exact one vendor, one commit request, one creation, matching consumed approval; 10/10 independent assertions passed |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v` (third run) | 0 | 5/5 passed in 19.683 seconds, with the same cases/assertions as failed attempts |

| `.\.venv\Scripts\python.exe -m backoffice demo --scenario conflicting-existing --provider scripted --approval fixture --run-dir work/demo-conflict` | 0 | Launched as an owned hidden process for memory sampling; raw actor exit 20 and `conflicting_existing` handoff; 4 scripted decisions; prior row unchanged; zero commit requests/creations; 5/5 verifier assertions passed |
| `.\.venv\Scripts\python.exe -m evaluation.verify --run-dir work/demo-happy` | 0 | Separate process; 10/10 final-state/authority assertions passed |
| `.\.venv\Scripts\python.exe -m evaluation.verify --run-dir work/demo-conflict` | 0 | Separate process; 5/5 unchanged-state/authority assertions passed |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v` (final venv) | 0 | 6/6 passed in 0.235 seconds |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests/contract -v` (final venv) | 0 | 4/4 passed |
| `doctor` with `PLAYWRIGHT_BROWSERS_PATH` set to `work/missing-browser` | 1, expected | Structured actionable startup error, no automatic install and no skipped browser check |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v` (final source) | 0 | 5/5 passed in 19.811 seconds after final completion-path guard and missing-browser diagnostic changes |
| `git ls-remote https://github.com/actions/checkout.git refs/tags/v6.1.0` | 0 | CI action SHA `d23441a48e516b6c34aea4fa41551a30e30af803` |
| `git ls-remote https://github.com/actions/setup-python.git refs/tags/v6.3.0` | 0 | CI action SHA `ece7cb06caefa5fff74198d8649806c4678c61a1` |
| `git diff --cached --check` | 0 | Staged source/docs have no whitespace errors; 25 reviewable files, caches and run data excluded |

The final checks pass **15 distinct M1 tests (6 unit + 4 contract + 5 browser)**. Repeated runs are not additional benchmark cases. The two demo journeys are development fixtures, not held-out model evaluation. The integration suite separately invokes the real CLI for pause, full-digest approval, resume and terminal replay; it asserts zero rows/received commit requests before approval and exactly one afterward. Adversarial local doubles exercise the actual request gate, with zero final POSTs reaching the portal. The verifier rejects deliberately corrupted final state despite the persisted success observation and actor claim.

## Environment and resource receipt

Executed on 2026-10-08, Asia/Calcutta. Implementation/check window began about 14:06; last heavy browser checks completed before 14:38. Actual environment: Microsoft Windows 11 Home Single Language, build 26200 (`platform.platform()` reports the Windows NT version as `Windows-10-10.0.26200-SP0`); Python 3.11.9; SQLite 3.45.1; Playwright 1.63.0; pyee 13.0.0; greenlet 3.3.2; typing-extensions 4.15.0; Chromium headless shell 153.0.8010.12 / Playwright revision 1243.

The exact named local resource grant was checked from raw ISO timestamps immediately before each download/browser batch. A conservative consumption window from 14:20:20 through 14:35:42 is 15.4 minutes including intervening coding/idle time, below the 30 active-minute cap. Package hashes were enforced by pip. Browser transfer used the official Playwright installer, which also installed its required FFmpeg/Winldd helpers. No full Chromium, Firefox, WebKit or model was downloaded.

- Wheels: 38,896,815 bytes total for the four selected Windows packages (about 37.1 MiB). Browser installer reported 114.6 MiB shell, 1.3 MiB FFmpeg and 0.1 MiB Winldd. Total transfer is approximately 153.1 MiB, plus small metadata/header traffic; browser sizes are rounded installer figures, not packet-level measurements. Lease cap: 400 MiB.
- Generated file sizes: `.venv` 131.11 MiB, `.cache` 273.70 MiB, `work` 0.15 MiB; total 404.96 MiB. Lease cap: 1,536 MiB. Git/source are additional small files.
- One browser ran at a time. A conflict-demo sampler followed the owned process descendant tree: 10 samples, up to 10 owned processes, sampled peak combined working sets 413.96 MiB. This is a sampled observation, not a continuous peak proof. Lease cap: 1,536 MiB.
- Cleanup inspection found zero remaining owned repository executables or portal processes. No unrelated process was stopped.
- Source/documentation search found no absolute personal paths; run data, venv, caches, local session state and repository-local instructions are ignored.

The repository had no initial HEAD commit. The staged M1 source-tree identity is recorded in the worker's coordination review receipt; no commit, push, remote CI execution or publication was performed.

## M1 review receipt

The independent M1 review reran units, contracts, browser integration, runtime doctor, happy/conflict demos, and independent verification. It reviewed the actual request gate and verifier's independence. Those checks apply to the M1 source snapshot, not the M2 changes prepared below.

## M2 source and lightweight checks

M2 source implements the published three-label-per-field vocabulary, reordered controls, accessible validation dialog, one local reauthentication, exact-existing/conflict handling, UI detail reconciliation after commit-response loss/restart, and fresh review/session/revision checks before approval consumption. The final request gate also persists dispatch consumption, blocking a second request even if a ticket is rearmed. Cancellation, step/time/token/evidence bounds, one protocol correction and bounded precommit read retries sit outside provider decisions.

The Ollama adapter is stdlib-only and opt-in, with literal loopback HTTP, no proxy/redirect, 16 KiB response bound and a total deadline. All transport checks use an ephemeral in-process HTTP double; they do not call Ollama or evaluate any model. Tests cover serialized tool schemas, assistant/tool/user feedback, unavailable and reported usage, malformed/multiple/unknown calls, endpoint errors, oversized data, timeout and trickled responses.

| Executed source/lightweight command | Exit | Observed result |
| --- | ---: | --- |
| `.\.venv\Scripts\python.exe -m evaluation.author_cases` | 0 | Ten development and thirty held-out definitions generated; no scoring |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v` | 0 | Final 11/11 tests passed in 0.752 s |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests/contract -v` | 0 | Final 16/16 tests passed in 1.034 s; only pure host checks and local HTTP doubles |
| `.\.venv\Scripts\python.exe -m compileall -q backoffice portal evaluation tests` | 0 | All Python sources compile; no portal or browser launched |
| `.\.venv\Scripts\python.exe -m backoffice --help` | 0 | CLI parser lists doctor/demo/review/approve/resume/cancel |
| `.\.venv\Scripts\python.exe -m evaluation.freeze --suite heldout` | 0 | 32 source/input/definition/dependency files SHA-256 frozen; expected counts 19 create / 2 existing / 9 handoff; scored=false |
| `.\.venv\Scripts\python.exe -m evaluation.freeze --suite heldout --check` | 0 | All 32 hashes match; held-out scoring marker absent |
| `git diff --cached --check` | 0 | Reviewable source/docs staged without whitespace errors; no commit/push |

These are **27 distinct lightweight tests**, including the ten earlier unit/contract tests. Reruns do not add distinct tests or benchmark cases. The first expanded contract pass also passed, but timed-out HTTP double teardown printed Windows `ConnectionAbortedError`; the fixture now catches the expected connection-close family and joins its owned handler threads. The assertions and deadline remained unchanged. An initial source patch was rejected before applying because delete/add operations targeted the same file; it was split into valid edits, with no execution or dependency change.

Development comparison source runs ten definitions for each of the reactive scripted policy and canonical fixed macro. Reports preserve all baseline failures and denominators, separate expected-outcome completion from safety, and record family counts and raw exits. Fault/reviewer settings remain in the external harness, never provider context. The thirty held-out definitions use new fictional values and combinations of the published vocabulary. Their author knows the families; they are a small transparent fixture set, not a statistical or language-generalization benchmark. Frozen hashes normalize CRLF to LF for Windows/Linux reproducibility. A replacement freeze is allowed only before first scoring; any post-scoring failure must remain in evidence.

At the M2 source checkpoint no M2 Chromium session or development task run had occurred. The separately authorized integration results are recorded below. Live-provider accuracy, M3 held-out/stress scoring and remote Linux CI were unexecuted at that checkpoint.

## M2 integration batch and outcomes

The installed pinned venv/headless shell was reused. From the repository root, `PLAYWRIGHT_BROWSERS_PATH` pointed to `.cache/ms-playwright`. The exact active `browser-backoffice-m2-integration` grant/expiry was parsed with timezone-aware Python before each command. These six commands ran sequentially:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v
.\.venv\Scripts\python.exe -m unittest discover -s tests/contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v
.\.venv\Scripts\python.exe -m evaluation.run --suite development --agents reactive-scripted,fixed-macro --out work/m2-eval
.\.venv\Scripts\python.exe -m evaluation.check_report --report work/m2-eval/report.json --require-cases 10 --require-safe
.\.venv\Scripts\python.exe -m evaluation.freeze --suite heldout --check
```

| Command above | Exit | Observed result |
| --- | ---: | --- |
| Unit suite | 0 | 11/11, 0.642 s test time |
| Contract suite | 0 | 16/16, 1.099 s test time; local HTTP round trips and host authority/budget checks |
| Browser integration suite | 0 | 15/15, 71.406 s test time; five M1 plus ten M2 tests |
| Development comparison | 0 | All 20 tasks present; reactive 10/10, fixed macro 4/10, all 20 safe |
| Independent report check | 0 | Exact denominators, reactive postconditions, canonical baseline success and all-run safety passed |
| Freeze check | 0 | All 32 hashes unchanged; held-out scoring marker absent |

This is **42 distinct tests (11 unit + 16 contract + 15 browser)**, separate from the twenty development tasks. No source correction, definition change, freeze replacement or additional scoring run was needed. Baseline failures remain in their original task directories and report. Per-case database/audit/trace/reviewer/verification evidence is retained under `work/m2-eval`; exact command logs and resource records are under `work/m2-execution`. Passing browser tests clean their temporary directories, with durable test output retained. None of those ignored local artifacts is staged for publication.

| Development postcondition | Reactive scripted | Fixed macro |
| --- | ---: | ---: |
| Create exact vendor | 6/6 | 1/6 |
| Recognize exact existing | 1/1 | 1/1 |
| Correct unchanged handoff | 3/3 | 2/3 |
| Total expected postconditions | 10/10 | 4/10 |
| Safety checks | 10/10 | 10/10 |

The macro passed the canonical control, conflict, exact-existing and stale-approval cases. Its label, modal, session, response-loss, pre-review restart and unsupported-field failures were safe but did not satisfy expected outcomes. The response-loss macro task wrote one correctly approved vendor before its restart policy handed off; it is retained as a failed completion, not counted as creation success. This authored development result measures specific rule/macro behavior, not model reasoning or generalization.

Across the twenty retained tasks, direct read-only workflow/portal audit inspection found eight vendor creations, eight received final POSTs, eight intents and eight dispatches, each at most one per task. There were ten grants, eight consumed approvals, two stale-approval handoffs and one reactive reauthentication. Wrong vendor rows, duplicate references and unauthorized creations were all zero. The reactive response-loss task resumed with raw exits `[11, 0]`, one vendor/POST and one consumed approval; pre-review restart also resumed `[11, 0]` with one final write. Each reactive no-change case received zero final POSTs.

Browser tests additionally verified consumed intent before dispatch remains consumed after restart and yields uncertainty handoff with zero POSTs; expired session after approval and explicit denial block submission; cancellation before write leaves zero rows, while cancellation after write leaves one approved row and reports unknown outcome. Actual generic-submit and changed-body requests were blocked before reaching the portal. The same test batch covers one reauthentication, exact-existing no resubmission, review freshness and immutable values despite injected page instructions. Unit/contract tests exercise persisted step/time/token/evidence limits, protocol correction, unchanged-cycle limits and bounded read retries.

Execution reused Windows 11 build 26200, Python 3.11.9, SQLite 3.45.1, the four existing pinned wheels and headless shell 153.0.8010.12/revision 1243. Measured child-command execution totaled **154.392 s**; the conservative interval including gaps was **221.936 s**, both below 900 s. At 200 ms intervals, 723 owned-process samples measured a **536.83 MiB** peak combined working set, with at most eleven owned descendants including CLI launchers. Sampling is not continuous peak proof. One browser ran at a time; each command ended with zero sampled owned PIDs remaining. Retained development evidence was **2.195 MiB**, far below the 256 MiB additional-disk cap; passing test temporary directories were removed. No download or model call occurred. Exact logs/receipt preserve per-command samples and durations.

The M2 lease was released after independent acceptance. The reviewer reproduced reactive 10/10 and macro 4/10, all twenty safe, with zero wrong/unauthorized rows or duplicates and all 32 frozen hashes unchanged. The review explicitly limited recovery evidence to orderly interruption/recreated runner: abrupt OS kill and power loss are unexecuted and can leave an exclusive lock requiring inspection. The frozen thirty-case suite was unscored at M2 acceptance.

## M3 source checkpoint

This section records the earlier source-only checkpoint. The separately authorized runtime batch follows below.

The authorized M3 source work adds `acceptance/` without editing any of the 32 originally frozen files. Its six Python harness/test files have a separate additive checkpoint that references the original freeze. No original freeze replacement, held-out definition/label change, provider/policy tuning or runtime dependency change occurred. The planned repeat CLI spelling is implemented as `acceptance.stress`, preserving six predefined cases times three while avoiding edits to the frozen `evaluation.run` module.

Prepared utilities cover fixed-order eighteen-run recovery repetition, retained-oracle/report/database audit for sixty comparison plus eighteen repeat runs, and fifteen isolated verifier corruptions against a positive creation. Reports reject missing/duplicate/reordered entries and preserve all baseline failures. The architecture/README now explain DOM control, original contribution, authority, persistence, tradeoffs, reproducible commands and the orderly-recovery boundary. The pinned read-only/secrets-free CI source includes final comparison and verifier sensitivity; no hosted job was started.

| Executed source/pure-unit command | Exit | Observed result |
| --- | ---: | --- |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v` | 0 | 11/11 in 0.917 s; no browser or HTTP batch |
| `.\.venv\Scripts\python.exe -m unittest discover -s acceptance/tests -v` | 0 | 8/8 in 0.789 s; synthetic metadata and development SQLite only |
| `.\.venv\Scripts\python.exe -m compileall -q acceptance` | 0 | All additive Python sources compile |
| `.\.venv\Scripts\python.exe -m evaluation.freeze --suite heldout --check` | 0 | Original 32 hashes match; held-out marker absent |
| `.\.venv\Scripts\python.exe -m acceptance.checkpoint --write` | 0 | Six additive code/test files checkpointed; original freeze not replaced |
| `.\.venv\Scripts\python.exe -m acceptance.checkpoint --check` | 0 | Original 32 and additive six files match; no changed files or scoring marker |

These are nineteen distinct pure tests for this source phase, with eight new tests. The synthetic control exercises all fifteen corruptions and verifies that the source SQLite/oracle bytes stay intact. It is not a held-out task, actor trajectory, browser evaluation or language-model score. The test uses fictional Cedar development values; metadata-only denominator tests create no held-out task database. Prior M2 contract/browser evidence remains valid for its accepted snapshot, and will be rerun only under the new lease.

At the M3 source checkpoint, no M3 browser, HTTP batch, full integration, held-out comparison, recovery repetition or real-run sensitivity/audit command had executed. Abrupt process termination, power loss, fresh final-checkout package installation, live Ollama runtime/model checks and hosted Linux CI also remained unexecuted. No weights, credentials or new packages were acquired.

The prepared final batch requests `browser-backoffice-m3-evaluation`: twenty active minutes, one browser sequentially, 1,536 MiB RAM, 512 MiB additional evidence disk and zero downloads/model calls. It will reuse installed pins, run the complete fifty-test total, sixty comparison tasks, eighteen repeat tasks, read-only retained-evidence audit, fifteen copied-run corruptions and fresh CLI demo directories. The M2 measured batch used 537 MiB sampled peak and about 2.2 MiB for twenty task directories; M3 resource figures are conservative bounds, not measured results. Exact commands and current source identity are recorded for local review. Work stops at `awaiting_integration_lease`; scoring requires a new grant and assignment.

## M3 executed final worker batch

Main accepted the source and assigned the exact nineteen-command batch under `browser-backoffice-m3-evaluation`. Each command checked the active worker/M3 lease and timezone-aware grant/expiry, remaining cumulative active budget, original 32-file freeze and six-file additive checkpoint immediately before execution. The existing pinned venv and `.cache/ms-playwright` were reused; no installation, download, model call or remote job ran. The actor, evaluator, case definitions, dependencies and both checkpoints stayed unchanged throughout scoring. All commands ran sequentially from the repository root with `PLAYWRIGHT_BROWSERS_PATH` set to the existing repository cache.

| # | Exact command | Exit | Observed result |
| ---: | --- | ---: | --- |
| 1 | `.\.venv\Scripts\python.exe -m evaluation.freeze --suite heldout --check` | 0 | Original 32 hashes unchanged; scoring initially unstarted |
| 2 | `.\.venv\Scripts\python.exe -m acceptance.checkpoint --check` | 0 | Original freeze and six additive files unchanged |
| 3 | `.\.venv\Scripts\python.exe -m backoffice doctor` | 0 | Existing Python/package/browser pins verified |
| 4 | `.\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v` | 0 | 11/11, 0.639 s test time |
| 5 | `.\.venv\Scripts\python.exe -m unittest discover -s acceptance/tests -v` | 0 | 8/8, 0.542 s test time |
| 6 | `.\.venv\Scripts\python.exe -m unittest discover -s tests/contract -v` | 0 | 16/16, 1.086 s test time |
| 7 | `.\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v` | 0 | 15/15, 70.364 s test time |
| 8 | `.\.venv\Scripts\python.exe -m evaluation.run --suite heldout --allow-heldout --agents reactive-scripted,fixed-macro --out work/m3-heldout` | 0 | 60 retained tasks; reactive 30/30, macro 3/30; all safe |
| 9 | `.\.venv\Scripts\python.exe -m evaluation.check_report --report work/m3-heldout/report.json --require-cases 30 --require-safe` | 0 | Held-out denominators, reactive outcomes and all-run safety passed |
| 10 | `.\.venv\Scripts\python.exe -m acceptance.stress --allow-heldout --out work/m3-repeat` | 0 | 18/18 expected outcomes and safety, six distinct cases times three |
| 11 | `.\.venv\Scripts\python.exe -m acceptance.stress --check --out work/m3-repeat` | 0 | Complete fixed-order repeats and all safety passed |
| 12 | `.\.venv\Scripts\python.exe -m acceptance.audit --heldout-out work/m3-heldout --stress-out work/m3-repeat` | 0 | 546 audit conditions: 420 for sixty comparison tasks, 126 for eighteen repeats |
| 13 | `.\.venv\Scripts\python.exe -m acceptance.sensitivity --source-run work/m3-heldout/reactive-scripted/heldout-01 --out work/m3-verifier-negative` | 0 | Positive control passed; 15/15 isolated corruptions rejected |
| 14 | `.\.venv\Scripts\python.exe -m backoffice demo --scenario happy --provider scripted --approval fixture --run-dir work/m3-quickstart-happy` | 0 | Fresh task directory; one exact approved creation; raw actor exit 0 |
| 15 | `.\.venv\Scripts\python.exe -m evaluation.verify --run-dir work/m3-quickstart-happy` | 0 | Independent creation/authority checks passed |
| 16 | `.\.venv\Scripts\python.exe -m backoffice demo --scenario conflicting-existing --provider scripted --approval fixture --run-dir work/m3-quickstart-conflict` | 0 | Fresh task directory; unchanged conflict, zero POSTs; raw actor exit 20 |
| 17 | `.\.venv\Scripts\python.exe -m evaluation.verify --run-dir work/m3-quickstart-conflict` | 0 | Independent unchanged-handoff checks passed |
| 18 | `.\.venv\Scripts\python.exe -m acceptance.checkpoint --check` | 0 | All 32+6 hashes unchanged; scoring marker present |
| 19 | `git diff --cached --check` | 0 | Staged source whitespace check passed |

There were **50 distinct tests: 11 unit, eight additive acceptance, sixteen contract and fifteen browser integration**. Tests are separate from sixty comparison tasks, eighteen repeats and two quickstart tasks. Passing browser tests remove temporary fixtures; their outputs remain in the logs. Every scored task directory and baseline failure remains intact under ignored `work/`, with databases, oracle, raw actor exits/restart receipts, events, review and verifier evidence. Full audit output and per-command execution/resource receipts are retained under `work/m3-execution`. No frozen-code repair or scored rerun was needed. Final documentation staging received an additional lightweight whitespace/checkpoint inspection.

| Held-out postcondition | Reactive scripted | Fixed macro |
| --- | ---: | ---: |
| Create exact vendor | 19/19 | 0/19 |
| Recognize exact existing | 2/2 | 2/2 |
| Correct unchanged handoff | 9/9 | 1/9 |
| Total expected postconditions | 30/30 | 3/30 |
| Safety checks | 30/30 | 30/30 |

| Held-out family | Reactive scripted | Fixed macro |
| --- | ---: | ---: |
| Authority | 2/2 | 0/2 |
| Duplicate/uncertain write | 6/6 | 3/6 |
| Injection/unsupported control | 4/4 | 0/4 |
| Labels/order | 6/6 | 0/6 |
| Session/restart | 6/6 | 0/6 |
| Validation | 6/6 | 0/6 |

Reactive no-write reasons were one approval denial, three invalidated approvals, one conflicting existing record, one uncertain commit, one unsupported required field and two rejected validations. The macro passed the two exact-existing cases and conflict; its 27 failures comprised 25 `unexpected_ui` and two `Review requires the real portal review page` handoffs. Those safe failures remain failures in the thirty-case denominator. Both approaches produced zero wrong vendor rows, unauthorized creations or duplicate references. The baseline's canonical success control was checked in the accepted development comparison; that condition is active only for development reports, not for this held-out report. The nineteen held-out creation variants are changed-label combinations and the macro created none.

The repeat order was `heldout-13,15,17,22,24,30` for each of three repetitions. Each repetition passed 6/6; all eighteen were safe. Repeats are additional reliability observations of six existing cases, not eighteen new held-out examples. The audit read all 78 retained task databases against frozen oracles and checked metadata/path, reported verifier result, provider identity, safety, reactive expected postconditions and bounded restart receipts. It is a worker-run independent domain-state verifier, not main's independent acceptance.

Sensitivity rejected missing/wrong/extra vendor state, duplicate reference, wrong actor outcome, unconsumed approval, wrong approval digest, changed review values, expired approval, missing dispatch, late grant, duplicate received commit, wrong created values, wrong draft identity and wrong revision. Corruptions occurred only in fifteen isolated copies of the successful `heldout-01` evidence; the positive control and source bytes were preserved.

Environment: Windows 11 build 26200, Python 3.11.9, SQLite 3.45.1, Playwright 1.63.0, pyee 13.0.0, greenlet 3.3.2, typing_extensions 4.15.0 and Chromium headless shell 153.0.8010.12/revision 1243. Subprocess execution totaled **366.485 s**; the conservative first-command-to-last-command interval including gaps was **890.929 s**, both below the 1,200 s active allowance. There were **1,727 samples** at approximately 200 ms intervals, a measured **580.92 MiB** peak combined working set and at most eleven sampled descendants including CLI launchers. Sampling is not continuous peak proof. The comparison/repeat/corruption/quickstart evidence and command logs occupied approximately **10.4 MiB** at collection, below 512 MiB; temporary passing-test data was removed and the existing venv/browser cache was reused. One browser ran at a time and no verified owned process remained after the batch.

Two administrative diagnostics are preserved. The first ignored lease wrapper used an incorrect resource field name and stopped before launching command 1; subsequent out-of-order attempts were refused. Only that scratch helper was corrected. The command 7 parent-PID-only sampler falsely associated two old HP background utilities with a reused CLI PID and conservatively included them in its 571.60 MiB sample. Creation-time inspection established that both utilities predated the test by hours; neither was touched. The ignored sampler then added process creation-time checks before comparison/repeats, whose peaks and cleanup used that correction. A later receipt-collection helper also corrected its lookup from `repeat` to the audit's `stress` key. These are scratch accounting errors, not failed acceptance commands or policy changes; raw diagnostics remain available.

Held-out scoring is now marked as started and frozen inputs stay fixed. The worker marks M3 ready and its lease release-ready, then stops for main's independent final review. Live Ollama/runtime/model evaluation, abrupt OS kill/power loss, fresh installation of the final checkout, hosted Linux CI and publication/deployment remain unexecuted. Recovery evidence remains limited to orderly interruption/recreated runner and deliberate response loss after commit. These same-author fictional scripted scores do not support production or live-model claims.

## Independent final local acceptance — 2026-10-08

A separate reviewer copied all 48 shipping source files without Git, generated evidence or browser state. The copied source reused the already installed pinned Python interpreter/packages and Chromium cache; no new installation or download was performed. All 18 documented commands returned 0: original/additive freeze checks, doctor, four test groups (11 unit, 8 acceptance, 16 local-provider contract, 15 browser integration), frozen comparison/report, recovery repeat/check, retained-state audit, corruption sensitivity, two fresh demos and their verifiers, final checkpoint.

Independent direct SQLite/JSON inspection passed 1,019 conditions across 80 raw states. The reviewer recomputed the 30/30 scripted versus 3/30 macro outcomes, all exact authority/commit ordering, immutable approved values and pre-existing records, single-dispatch bounds, six identical three-repeat recovery states and both quickstart outcomes. All 15 deliberate corruptions were rejected without changing their source positive run. Every original and additive source hash remained unchanged. Only README, architecture and this evidence file changed for the final handoff; a final source-only checkpoint check passed. Official CI action tag-to-commit pins were checked with read-only upstream queries.

This verifies the agreed authored offline workflow. No live model inference, arbitrary website evaluation, hosted CI/Linux execution, final fresh package installation, abrupt OS kill/power-loss recovery, production authentication or hostile-code isolation was tested. CI replay is the same public fixture suite. Sampled memory is not a continuous peak guarantee.

## Public source release — 9 October 2026

All three local MVP milestones passed independent acceptance on 8 October 2026, including final documentation review. The review was executed separately from the implementation worker and included documented quickstarts, meaningful success/failure tests and direct domain-state checks. The results and limitations above remain unchanged.

This source release includes application code, authored fixtures, evaluator/tests, quickstart, architecture, license/attribution and the prepared CI workflow. Private orchestration records, machine-specific paths, runtime caches and generated local runs are excluded. Offline scripted/rule/replay outcomes and local provider doubles do not establish live model quality, employer adoption or production impact. Hosted CI results are available in this repository's Actions tab after publication; historical local reports retain their original execution dates.
