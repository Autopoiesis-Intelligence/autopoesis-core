# Implementation Gap Analysis

**Scope:** Read-only inspection of repository files on `main` during the architecture baseline review.  
**Purpose:** Separate verified code structure from design goals not yet demonstrated.  
**Evidence limit:** This is a source inspection, not a fresh test or CI run.

## Snapshot inspected

- `autopoesis/core.py` — SHA `968ef22efc593f1919a966898efde7bddf6f7b10`
- `autopoesis/executor.py` — SHA `3ecb9b7f6dd45c13a7790c90df5d590283df0c77`
- `autopoesis/task_queue.py` — SHA `5e3828613f9197d315391b1e7467634ee923c715`
- `run_tasks.py` — SHA `71fa1b1c71b7a04b54f2f4909da04b327804965a`
- `tests/test_core.py` — SHA `9075c678a801aebcb7662ca53ef42ca75ceb4f6f`
- `.github/workflows/ci.yml` — SHA `d419d61bfd81aeb2ab134a3eda09fe40971c86a9`

These are file blob SHAs, not a repository commit SHA or CI run ID.

## Implemented in inspected source

1. Canonical JSON serialization rejects non-JSON values and non-finite numbers; SHA-256 provides a stable state digest.
2. The basic `evolve` function accepts a digest-changing candidate and rejects a no-op.
3. Task execution is restricted to explicitly implemented task types; task descriptions do not become arbitrary shell commands.
4. Discovery scans Python sources for TODO/FIXME/HACK markers and missing conventional test filenames.
5. Queue merge deduplicates IDs, preserves existing statuses, and appends lifecycle history.
6. The built-in writer generates a narrow import-smoke-test artifact, checks hashes/path scope/syntax, and can write it only into a temporary sandbox through the current task.
7. CI is configured to run unit tests and the task runner on Python 3.12 for pushes and pull requests targeting `main`.

## Gaps relative to the architecture baseline

### GAP-01 — No operational homeostasis controller

No explicit X/R measurement contract, viability thresholds, stability monitor, or automatic rollback controller is present in the inspected `core.py` and `run_tasks.py`. The architecture document correctly treats X/R as undefined until units, sampling, bounds, and tests are specified.

### GAP-02 — State change is not fitness improvement

`evolve(current, candidate)` accepts any valid JSON candidate whose digest differs. It does not compare objective fitness, validate domain invariants, or establish that the candidate is safer or more useful. Digest inequality proves difference, not improvement.

### GAP-03 — Sandbox application is not candidate evaluation

The current `apply_test_patch_sandbox` task writes a generated test file into a temporary directory and removes that directory afterward. The inspected implementation explicitly does not execute generated code or run the generated test inside that sandbox. Therefore it proves bounded file creation, not that the proposed change passes tests.

### GAP-04 — No automatic repository patch acceptance

The current writer creates an artifact; the sandbox task applies it only to a temporary directory. The inspected runner does not apply the patch to the repository working tree or commit it. This is a useful safety boundary, but the end-to-end evolution cycle is not yet implemented.

### GAP-05 — Queue persistence differs between local and CI runs

The queue file persists between local executions when retained on disk. The workflow uploads `TASK_QUEUE.json` as an artifact, but each GitHub Actions run begins from a clean checkout and the workflow does not restore the previous artifact. Thus the artifact is a run snapshot, not a cross-run persistent queue.

### GAP-06 — Audit history is not yet a full causal lineage

Queue history records candidate addition and status changes. The inspected code does not yet connect an accepted state to its parent digest, evaluator version, fitness measurements, test evidence, approval identity, and resulting commit SHA in one immutable evolution record.

### GAP-07 — Status and result claims need stricter semantics

The runner labels a task `PASS` when its implemented handler returns without raising. For proposal tasks, this means the proposal was produced, not that the proposed capability exists. Consumers must interpret status alongside task type and result semantics.

## Recommended next sequence

1. **SEQ 1 — Test and evidence baseline:** inspect current default-branch head and latest CI run; run existing tests in CI and preserve exact commit/run identifiers.
2. **SEQ 2 — Define state transition contract:** keep deterministic digest identity separate from fitness; specify validators and objective comparison before any candidate can be accepted as an improvement.
3. **SEQ 3 — Implement measurable safety envelope:** add a deterministic viability evaluator with explicit metrics and bounds. Do not invent an X/R formula without a defined operational model.
4. **SEQ 4 — Make sandbox evaluation real:** run allowed checks in an isolated workspace with time/resource limits and record outputs. Keep generated code untrusted.
5. **SEQ 5 — Record lineage:** link parent state, candidate, evaluator version, checks, decision, and resulting digest.
6. **SEQ 6 — Choose queue persistence deliberately:** use a durable storage mechanism or an explicit restore step; do not confuse uploaded artifacts with automatically restored state.
7. **SEQ 7 — Consider governed patch application only after evidence:** add an explicit acceptance boundary and tests for rejection, rollback, and repository cleanliness.

## Current conclusion

The repository contains a useful deterministic starter, task intake, queue, and narrowly scoped patch-artifact mechanism. The inspected source does **not** yet establish a self-evolving core with homeostasis, fitness-based selection, executed sandbox evaluation, automatic accepted-state commit, or full cross-run lineage. These are implementation gaps, not reasons to discard the starter.


## Follow-up: evaluator hardening prototype (2026-10-18)

The evaluation prototype has since been extended on the research branch. This section records implementation changes, not a claim of passing CI.

- Missing invariant lists now return `UNRESOLVED / INVARIANTS_MISSING` instead of passing vacuously.
- Homeostasis receives both parent and candidate states, allowing transition-aware checks.
- Evaluator, invariant, and homeostasis callbacks receive defensive copies of state/fixtures so ordinary in-place mutation does not alter caller-owned objects.
- State payloads have configurable maximum canonical JSON byte size and nesting depth.
- Tests were added for empty invariants, transition-aware homeostasis, callback mutation isolation, state size/depth bounds, and the improvement threshold boundary.
- The decision receipt remains an in-memory object; durable receipt persistence is still not implemented.
- Callback copying does not prove purity, determinism, resource isolation, or that the callable actually matches the declared evaluator ID/version. Those remain explicit trust/evidence gaps.
- CI run #81 on exact head `ff518806d05986a2ce2eafb4519056bc51936456` completed **SUCCESS**: unit tests and file-based tasks passed. Run: https://github.com/Autopoiesis-Intelligence/autopoesis-core/actions/runs/39128614451.
- A later viability implementation was added after that CI run. Its current head must receive its own CI run; run #81 does not cover those later files.

Next evidence requirement: obtain a CI run for the exact current branch head, inspect its result, and then run an end-to-end runtime demonstration separately. A passing unit suite alone would not establish durable receipts, isolated execution, or a complete self-evolution loop.


## SEQ B: explicit viability-envelope prototype (implementation added; CI pending)

Added `autopoesis/viability.py` with `MetricBound`, `ViabilityPolicy`, and `evaluate_viability`.

- Every metric must have a name, ID, version, unit, and at least one explicit minimum/maximum bound.
- The policy must contain at least one uniquely named metric; no default metric, X/R formula, entropy score, or fitness objective is invented.
- The supplied measurer evaluates both parent and candidate. Non-finite/non-numeric values, missing policy/measurer, malformed policy, or callback errors return `UNRESOLVED`.
- A candidate outside any declared bound returns `REJECTED`; otherwise it returns `ACCEPTED` for the viability gate only. This is not final candidate acceptance, fitness improvement, execution permission, or commit authority.
- Parent measurements are recorded for comparison. The parent may already be outside the envelope; a candidate can pass this gate if it satisfies all declared bounds, which permits a move back into a viable region.
- Inputs are passed to the measurement callback as defensive copies. This does not prove callback purity, determinism, or resource isolation.
- The returned receipt is currently in memory; durable receipt storage and end-to-end runtime proof remain missing.
- Tests in `tests/test_viability.py` cover explicit bounds, violations, missing evidence, invalid policies, non-finite values, and callback input isolation. These tests are authored but not yet CI-proven at the current head.

Evidence ladder: DESIGN = defined; IMPLEMENTED = source and tests added; REACHABLE = exported public API; RUNTIME = pending; PERSISTED = pending; AUDITED = partial source review; CI_PROVEN = pending for the current head.


## SEQ C: viability gate wired into the file-based runner (CI pending)

- Added `verify_viability_gate()` to `run_tasks.py`. It exercises one candidate that meets explicit bounds and one candidate that violates the memory bound.
- Added task type `verify_viability_gate` to `execute_task` and registered `CORE-007` in `TASKS.json`.
- Added tests for both decision outcomes and for reachability through the task dispatcher.
- The runner reports this as a viability-only check. It explicitly does not grant fitness acceptance, code execution permission, or repository commit authority.
- This demonstrates that the viability module is reachable through the configured file-task interface once CI passes. It does not demonstrate real process-memory measurement: the runner uses fixed synthetic state fields and an injected deterministic measurer.
- Exact implementation head at the time of this note: pending confirmation after documentation commit. CI for the new runner integration is not yet observed.


## SEQ D: persistent decision journal (implementation added; CI pending)

- Added `autopoesis/receipt_store.py` with a versioned JSON snapshot, sequential entries, unique receipt IDs, canonical JSON digests, and a SHA-256 previous-entry chain.
- Writes use a temporary file in the same directory followed by `os.replace`, so readers should see either the previous or replacement snapshot rather than a partially written JSON document under ordinary local-filesystem semantics.
- Loading verifies schema version, sequence numbers, unique IDs, previous-digest links, and each entry digest. Tampering with a record without recomputing the chain is detected.
- The public API is exported from `autopoesis`; tests cover round-trip persistence, hash-chain linkage, tampering, duplicate IDs, and missing IDs.
- Explicit limits: this is integrity-evident, not tamper-proof; an actor who can rewrite the entire journal can recompute the hashes. The implementation assumes a single writer and does not claim cross-process locking, fsync-level durability, trusted timestamps, or external anchoring.
- The journal stores caller-supplied decision records; it does not itself authenticate evaluator identity or prove that a decision's claimed checks actually ran.
- Current exact branch head and CI must be checked after these commits. Passing tests would prove this implementation's tested behavior, not production persistence guarantees or end-to-end autonomous evolution.


## SEQ E: evaluation receipt connected to durable journal (CI-proven on current recorded head)

- Added runner task `verify_evaluation_receipt_persistence` and registered it as `CORE-009`.
- The task calls the actual `evaluate_transition` function with a synthetic parent/candidate pair, explicit policy, invariant, homeostasis check, evaluator, and fixtures.
- It persists the resulting receipt, reloads the journal, and checks that the full receipt survives round-trip without semantic loss, including decision, policy/evaluator identity, state digests, and fixture digest.
- Tests cover direct execution and reachability through the file-task dispatcher.
- This is stronger than storing a hand-written decision-only record, but remains a synthetic integration check. It does not establish that production decisions are automatically journaled, evaluator code is authentic, or any candidate was executed in an isolated runtime.
- Exact-head CI evidence was subsequently obtained in run #109, ID `39129341281`, on SHA `c31ae4c3fe9cd62b0ff77d7258a9a15e466a47d3`; unit tests, file-based tasks, and artifact upload all succeeded.
- The same run covers the independent-process journal test from SEQ F. It proves the test passed on the CI filesystem for this exact SHA; it does not establish crash-proof durability, production storage availability, or multi-writer safety.


### SEQ E follow-up: typed evaluation-receipt API

- Added `append_evaluation_receipt(path, receipt, receipt_id=...)` as the explicit adapter between `evaluate_transition` output and the durable journal.
- The adapter requires the evaluation receipt's schema, candidate and state identity fields, policy/evaluator identity and versions, decision, and reason. It rejects unsupported schema versions and unknown decisions.
- The runner integration now uses this typed adapter instead of writing the evaluation receipt as an untyped generic record. A test rejects incomplete receipts.
- Shape validation does not authenticate the evaluator or prove the receipt was generated by the declared code. The journal remains local and single-writer.


### SEQ F: independent-process persistence test (CI-proven on recorded head)

- Added a test that launches one Python process to write a journal entry and a second independent Python process to load and verify it.
- CI run #109 (`39129341281`) passed on exact HEAD `c31ae4c3fe9cd62b0ff77d7258a9a15e466a47d3`, including the unit-test step containing this test.
- This proves persistence across independent process invocations on the CI filesystem, not crash-proof durability, multi-writer safety, or production storage availability.


## SEQ G: exact-head CI reconciliation and candidate-execution boundary

- Rechecked PR #3 and its current head. At the time of this check, the PR was open and draft, based on `main`, with HEAD `c31ae4c3fe9cd62b0ff77d7258a9a15e466a47d3`; GitHub reported `mergeable: true`.
- Exact-head CI run #109 (run ID `39129341281`) completed successfully. The unit-test step, file-based task step, and artifact-upload step all reported success.
- This reconciles the previous SEQ F note that CI was pending. The prior run #96 on SHA `a561d1de02eba99651ccc35140bbe1159b536672` remains historical evidence only; run #109 is the relevant evidence for the recorded head.
- The executor still validates patch hashes, path scope, and Python syntax, and can write artifacts into a temporary sandbox. It explicitly does not execute generated code.
- Next implementation boundary: do not equate a subprocess with a secure sandbox. Before enabling candidate-code execution, define and test a fixed command allowlist, time and output limits, clean environment, disposable workspace, filesystem/network/credential isolation, and auditable exit evidence. If the host cannot enforce OS-level isolation, keep execution disabled and label the capability as bounded subprocess execution rather than secure isolation.
- Status: exact-head CI = CI_PROVEN for the recorded SHA; candidate execution = NOT IMPLEMENTED; secure isolation = NOT PROVEN; autonomous self-improvement = NOT PROVEN.


## SEQ H: fail-closed candidate execution policy contract (implementation added; CI pending)

- Added `autopoesis/execution_policy.py` with an explicit policy shape: fixed command profile, bounded timeout, bounded output, and declared network, secret, filesystem, and OS-sandbox controls.
- The policy assessor rejects absent or incomplete policies. The only currently recognized command profile is `python-unittest-v1`; arbitrary shell profiles are rejected.
- A complete declaration returns `POLICY_COMPLETE_NOT_AUTHORIZED`, never permission to execute. The boolean isolation fields are caller declarations and do not prove that the operating system enforces those controls.
- Added runner task `verify_candidate_execution_boundary`, registered as `CORE-010`, with tests for fail-closed behavior and task reachability.
- No candidate code is executed by this sequence. No sandbox adapter, OS-level isolation, network denial, credential exclusion, resource enforcement, or execution receipt has been implemented.
- Required next step: obtain CI on the exact resulting HEAD. After that, research the host's enforceable isolation options before implementing any executor. If isolation cannot be verified, candidate execution remains disabled.
- Evidence status for this sequence before CI: DESIGN = defined; IMPLEMENTED = added; REACHABLE = wired into task runner; RUNTIME = pending CI; PERSISTED = not applicable to policy assessment; AUDITED = partial source review; CI_PROVEN = pending.


## SEQ I: host isolation-tool inventory (implementation added; CI pending)

- Added `inspect_host_isolation_capabilities()` to `autopoesis/execution_policy.py`. It records the host platform, Python version, and paths of known candidate isolation tools found through executable lookup (`bwrap`, `firejail`, `nsjail`, `docker`, `podman`, `unshare`, `sandbox-exec`).
- The inventory does not execute these tools or candidate code. Its status is always `NO_VERIFIED_SANDBOX`; discovered tool presence is explicitly not treated as proof of enforcement.
- Added runner task `verify_host_isolation_inventory`, registered as `CORE-011`, and tests for its fail-closed semantics and task reachability.
- Runtime inventory results must be read from the exact-head CI artifact/log before saying which tools are present in that runner. Presence alone still does not establish kernel support, permissions, effective network/filesystem restrictions, credential exclusion, or resource limits.
- Current evidence before CI: DESIGN = defined; IMPLEMENTED = added; REACHABLE = wired into task runner; RUNTIME = pending exact-head CI; PERSISTED = task output is written by the normal runner to `RESULTS.json` and CI uploads it as an artifact, but artifact retrieval has not yet been checked; AUDITED = partial source review; CI_PROVEN = pending.
- No candidate code is executed, and no execution authority is granted by this sequence.


## SEQ J: bounded host isolation runtime probes (implementation added; CI pending)

- Extended the host diagnostic with fixed, non-shell probes for Docker daemon reachability, Podman runtime availability, and user-namespace support.
- Each probe has a 1–5 second timeout, bounded captured output, and a minimal environment. Arguments are hard-coded; task text cannot supply a command or arguments.
- These probes do not execute generated candidate code. They test whether selected host facilities respond, not whether an adversarial workload is safely contained.
- Added runner task `verify_isolation_runtime_probe`, registered as `CORE-012`, and tests for diagnostic-only semantics, bounded parameters, and task reachability.
- The earlier CI artifact on SHA `c0675c224de1e14532b3a582f95a931eb52b22f3` showed executable paths for Docker, Podman, and `unshare`, but did not prove daemon/runtime access or sandbox enforcement. SEQ J must obtain a new exact-head CI artifact to observe those fixed probes.
- No candidate execution is enabled. A future sandbox adapter must still be tested against filesystem escape, network access, credential visibility, process/resource exhaustion, and cleanup.
- Evidence before CI: DESIGN = defined; IMPLEMENTED = added; REACHABLE = wired into runner; RUNTIME = pending exact-head CI; PERSISTED = task output is included in CI artifact when successful; AUDITED = partial source review; CI_PROVEN = pending.
