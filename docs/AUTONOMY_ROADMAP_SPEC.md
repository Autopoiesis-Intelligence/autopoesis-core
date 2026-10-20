# Autonomy Roadmap — Requirements Specification

**Status:** Requirements draft. This document does not prove implementation or passage of any gate.  
**Repository:** `Autopoiesis-Intelligence/autopoesis-core`

## 1. Objective

Define ordered, testable requirements for progressing from a manually started file-driven task runner to bounded autonomy: durable state → candidate discovery/selection → isolated change generation → bounded execution → independent verification → governed acceptance → persistent progress → bounded unattended trials.

Autonomy is not proven by a green unit-test run, synthetic fixture, queue status, percentage estimate, or a claim in chat. Evidence must be tied to exact commits, CI runs, runtime results, and artifacts.

## 2. Invariants and non-goals

- No arbitrary shell/Python execution from task descriptions or queue data.
- No direct writes to protected source state or default branch by an unverified candidate.
- No silent conversion of malformed, unreadable, or invalid persisted state into an empty queue.
- No no-op counted as evolution/progress; synthetic results are not real-world improvement.
- Selection, verification, execution, approval, commit, and merge remain distinct.
- Missing, stale, contradictory, or inconclusive evidence fails closed.
- No merge, release, or privilege escalation without an explicit policy gate.
- Keep external model/provider calls replaceable and outside the trusted core unless separately justified.

## 3. Staged requirements and acceptance gates

### A0 — Baseline reconciliation
**Requirements:** Record exact current PR heads/bases, workflow runs, task types, queue schema, permissions, persistence and artifact behavior. Map each claim to code/tests/runtime evidence. Keep main unchanged during audit.  
**Acceptance:** Baseline names exact SHAs and links; stale CI and inherited claims are excluded from current-head proof; unknowns are listed.

### A1 — Durable, fail-closed state
**Requirements:** Distinguish an allowed first-run missing file from read/permission/JSON/schema/history errors. Atomic replacement and cleanup on failures. Document durability guarantees, including directory sync where required/supported. Choose single-writer, lock, or optimistic conflict detection to prevent lost updates and stale overwrites.  
**Acceptance:** Tests cover missing/unreadable/malformed/invalid state, write/flush/replace failure, cleanup and concurrent writers. Corrupt/ambiguous state stops the run; it never resets progress silently.

### A2 — Snapshot restore and provenance
**Requirements:** Bind restore to expected repository, workflow, run ID, successful conclusion, source SHA and unique unexpired artifact. Validate required files, manifest, schema, sizes and hashes before installation. Record source run/SHA, artifact identity, manifest digest, restored queue digest and result. Clearly distinguish internal consistency from trusted authorship; use independent archive-digest verification or signed provenance if the threat model requires it.  
**Acceptance:** End-to-end negative cases cover failed/wrong workflow, repo/SHA/ID mismatch, missing/expired/duplicate/unbound artifact, malformed/missing files and digest/size mismatch. Failed restore cannot execute tasks. Synthetic restore remains labeled synthetic.

### A3 — Closed task lifecycle
**Requirements:** Specify legal transitions, retries, attempt limits, terminal states and interruption recovery. Separate candidate, eligibility, execution, verification, acceptance and completion. Define when DONE is allowed; persist evidence and transitions with recoverable transaction semantics. Make duplicate submissions idempotent.  
**Acceptance:** Transition table/schema and tests cover illegal transitions, duplicates, retries, interruption and replay. A narrow PASS does not automatically mean task completion; replay does not create false progress.

### A4 — Candidate discovery and selection
**Requirements:** Generate candidates from inspectable sources (defects, missing tests, failed checks, bounded static findings). Record rationale, source evidence, affected paths, expected benefit, risk and cost where available. Apply deterministic eligibility/prioritization; explain selection and deferrals. Stop for human input if evidence is insufficient.  
**Acceptance:** Same snapshot and policy produce reproducible identities/decisions. Selection is auditable and separate from execution/verification. Empty, duplicate, invalid and conflicting candidates are tested; no-work does not manufacture progress.

### A5 — Bounded change generation
**Requirements:** Define allowed paths/file types/size limits/patch format/postconditions. Reject traversal, symlinks, unexpected files, duplicates, overwrites, malformed patches and policy violations. Work only in a disposable workspace or isolated branch. Preserve immutable patch artifact and digest tied to parent commit. Treat model output as untrusted.  
**Acceptance:** Adversarial tests cover escape, symlink, overwrite, oversized/malformed patch and disallowed paths. Rejected patches leave accepted state unchanged. Generation alone is not progress.

### A6 — Isolated execution and resource limits
**Requirements:** Run only permitted tests in a disposable environment. Define time, CPU/memory where supported, environment, filesystem/network access and cleanup. Do not call a temporary directory a hardened sandbox. Treat generated imports/code as potentially unsafe. Capture commands, configuration, exit/timeout and relevant output without secrets.  
**Acceptance:** Timeout and cleanup tests pass; blocked/unresolved capabilities are explicit; executed test set is reproducible; verification level is accurately labeled.

### A7 — Independent verification and evidence binding
**Requirements:** Check explicit acceptance criteria independently of the generator. Bind evidence to repository, parent SHA, candidate, patch digest, test command/config, resulting workspace/commit SHA and verifier version. Distinguish structural, unit, integration, runtime, persistence, audit and CI evidence. Preserve FAIL/inconclusive; never infer PASS from missing evidence.  
**Acceptance:** Tampering/missing/stale/mismatched evidence is rejected. Results say what was tested and what remains unproven. Verification evidence is not execution authority or merge approval.

### A8 — Governed acceptance and commit
**Requirements:** Define policy for accepting changes, commits, PRs and review. Separate verification, approval, authority, commit and merge. Enforce least privilege and branch protections. Require explicit authorization beyond pre-approved scope. Record parent, resulting SHA, evidence, policy version and decision provenance.  
**Acceptance:** Unverified, stale, unauthorized or out-of-policy changes cannot reach protected source state. Tests passing cannot alone trigger merge/deploy. Every accepted change is reviewable and reversible.

### A9 — Persistent progress and recovery
**Requirements:** Measure progress by accepted, independently verified changes—not task count, PASS count or queue status. Recover after process/runner loss, duplicate dispatch and restore. Prevent stale state regression. Separate synthetic fixtures from evolution records. Publish machine-readable proven/failed/blocked/unknown status.  
**Acceptance:** Crash/restart and duplicate-run tests show no false completion or lost accepted evidence. Progress is reconstructable from records and exact commits. No-op runs do not increase progress.

### A10 — Bounded autonomous orchestration
**Requirements:** Specify triggers, next-task selection, retries, budgets and stop conditions. Limit task count, wall time, resources, retries and change scope. Stop on repeated failure, contradictory state, missing provenance, policy violation, exhausted budget or uncertain verification. Prevent overlapping runs. Provide audit trail and kill/disable control. Scheduling must be an explicit workflow/adapter, not a hidden clock/global operator.  
**Acceptance:** Full loop runs without step-by-step intervention only inside pre-authorized scope. Limits and stops are tested; disable stops new work while preserving evidence; failures never cause silent reset or weakened checks.

### A11 — Sustained unattended trial
**Requirements:** Run multiple independent cycles/restarts, including failures, interruption, restore and recovery. Predeclare trial duration/cycle count and success thresholds. Review all changes under the same acceptance policy; document failures and near misses.  
**Acceptance:** Trial report identifies exact SHAs, run IDs, artifacts, candidates, patch digests, verification records and accepted commits. No unauthorized write, unverified acceptance, silent state loss or false progress occurs. Only then may bounded autonomy be claimed, limited to tested scope.

### A12 — Controlled expansion
**Requirements:** Expand task types/write scope one capability at a time. Re-run relevant threat-model, persistence, provenance and recovery gates. Maintain rollback and policy version.  
**Acceptance:** Each new capability has bounded contract, threat model, tests, runtime evidence and rollback. Declared autonomy never exceeds the scope proven by current evidence.

## 4. Evidence ladder and status vocabulary

Report separately:
1. **DESIGN** — requirement documented.
2. **IMPLEMENTED** — code exists at exact SHA.
3. **REACHABLE** — workflow/runner path can invoke it.
4. **RUNTIME** — observed execution evidence exists.
5. **PERSISTED** — state/evidence survives restart/restore.
6. **AUDITED** — boundaries and negative cases reviewed.
7. **CI_PROVEN** — relevant CI passes on the exact SHA.

A status field saying PASS is not proof by itself. Every proof claim names exact SHA, CI run, relevant artifact/result and the behavior demonstrated. Local/unit/synthetic PASS does not imply runtime autonomy.

## 5. Milestones

- **M1 — Reliable automation:** explicit tasks run, failures are visible, persistence and restore fail closed.
- **M2 — Bounded autonomy:** candidate selection, isolated change, execution, independent verification and governed acceptance form one auditable bounded loop.
- **M3 — Sustained bounded autonomy:** predeclared unattended trial passes across multiple cycles and restarts.
- **M4 — Expanded autonomy:** additional task types or write permissions pass separate evidence-backed gates.

Milestones are acceptance gates, not calendar promises. Estimates must be updated from repository evidence.

## 6. Execution order

1. Reconcile current remote refs and CI (A0).
2. Audit state reads/writes and concurrency (A1).
3. Audit restore negative paths and artifact provenance (A2).
4. Finalize lifecycle/completion semantics (A3).
5. Implement and verify one stage at a time, preserving exact SHA and CI evidence.
6. Do not enable unattended orchestration before relevant A1–A9 gates pass.
7. Do not claim sustained autonomy before A11 trial passes.

## 7. Required stage report

For each stage record: stage ID/version; status (`NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `PASS`, `FAIL`); branch and exact SHA; PR and CI run URLs/IDs; tests/artifacts examined; passed/failed criteria; proven facts, unproven claims, rejected approaches and limitations; next bounded action and estimate in minutes; and whether evidence is synthetic or representative.

Do not promote a stage without evidence appropriate to that stage.

## 8. Initial repository note

This specification is intended to be added on a documentation branch based on the integration PR head. It does not implement or certify any stage. First reconcile the exact remote state of PR #10 and PR #12, then continue A1/A2. Main must remain unchanged unless separately authorized.
