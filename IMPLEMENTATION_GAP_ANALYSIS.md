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
