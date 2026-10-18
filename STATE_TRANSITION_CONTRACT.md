# State Transition Contract

Status: design contract; not an implementation claim.

## Purpose

Define the minimum deterministic contract for deciding whether a proposed state transition is safe and beneficial. A changed state is not, by itself, an improvement. Candidate generation, candidate evaluation, and repository commit are separate operations.

## Current boundary

The current `evolve(current, candidate)` primitive compares canonical state digests and rejects a no-op. It does not establish fitness improvement, enforce domain invariants, execute generated code, or authorize a repository commit. This contract must not be described as implemented until code and tests demonstrate it.

## Inputs

A transition evaluation receives:

- `parent_state`: the currently accepted state.
- `candidate_state`: a proposed replacement state.
- `evaluation_policy`: an explicit, versioned policy defining validation, invariants, metrics, objective direction, minimum improvement threshold, and resource limits.
- `evaluation_context`: deterministic fixtures and evaluator versions needed to compare parent and candidate fairly.

No hidden clock, implicit global selector, external LLM, or undeclared runtime input may influence a core decision.

## Required evaluation order

1. **Canonicalize and validate representation.** Accept only supported JSON-compatible values. Reject non-finite numbers, unsupported types, malformed input, and states exceeding configured size/depth limits.
2. **Verify parent identity.** Recompute the parent digest and compare it with the expected parent digest. A stale parent is rejected; it must not overwrite newer accepted state.
3. **Detect no-op.** If canonical parent and candidate digests match, return `REJECTED` with reason `NO_STATE_CHANGE`.
4. **Check invariants.** Evaluate all required, explicitly configured invariants. Any failed invariant rejects the candidate. A missing required invariant result is `UNRESOLVED`, not a pass.
5. **Check homeostasis envelope.** Evaluate configured safety/resource bounds independently from fitness. Missing required measurements or incomparable measurement contexts are `UNRESOLVED`; a bound violation is `REJECTED`.
6. **Evaluate fitness.** Use a named, versioned evaluator and explicit objective direction. Evaluate parent and candidate on the same deterministic fixtures and comparable conditions. If the evaluator, baseline, candidate result, or policy is missing or incompatible, return `UNRESOLVED`.
7. **Apply acceptance threshold.** Accept only if all required checks pass and the candidate improves the configured objective by at least the policy's explicit minimum delta. A regression or insufficient improvement is `REJECTED`. Do not infer an objective or threshold.
8. **Emit a decision receipt.** Record the evidence for the decision. Evaluation itself must not mutate the accepted state or commit repository changes.

## Decision semantics

- `ACCEPTED`: every required validation and safety check passed, evaluation is comparable and reproducible under the declared policy, and the improvement threshold is met.
- `REJECTED`: a deterministic disqualifying condition occurred, such as invalid representation, stale parent, no-op, invariant violation, safety-bound violation, regression, or insufficient improvement.
- `UNRESOLVED`: required evidence is absent, incompatible, non-comparable, or not reproducible. This state grants no permission to apply or commit the candidate.

Fail closed: both `REJECTED` and `UNRESOLVED` preserve the previously accepted state.

## Homeostasis is not fitness

Homeostasis defines explicit safety and operating bounds; fitness ranks candidates within those bounds. They must remain separate decisions. No universal formula for `X`, `R`, entropy, or fitness is assumed here. Those concepts become operational only after their representation, units, measurement procedure, and policy version are specified. Until then, any numerical claim about them is a hypothesis, not measured runtime evidence.

## Decision receipt

The minimum receipt should contain:

- `schema_version`
- `candidate_id`
- `parent_state_digest`
- `candidate_state_digest`
- `evaluation_policy_id` and `evaluation_policy_version`
- `evaluator_id` and `evaluator_version`
- baseline and candidate measurements, including units and fixture/context identifiers
- computed delta and configured acceptance threshold, where applicable
- invariant and homeostasis check results
- decision (`ACCEPTED`, `REJECTED`, or `UNRESOLVED`) and stable reason code
- reproducibility inputs or references to them

A receipt records a decision; it does not prove code execution, persistence, repository commit, or runtime behavior. Timestamps may be supplemental metadata, but must not serve as trusted authority unless a trusted-time source is explicitly designed and verified.

## Separation of responsibilities

- **Generate:** produce a candidate without changing accepted state.
- **Evaluate:** validate and emit a decision receipt without changing accepted state.
- **Apply to sandbox:** materialize an accepted or test-authorized candidate in an isolated workspace; never treat materialization as execution.
- **Verify:** run the declared checks and retain their results.
- **Commit:** require a separate explicit policy gate that binds the accepted candidate to its parent digest and verification evidence.
- **Persist:** store state and receipts durably; demonstrate reload/recovery separately from in-memory success.

No task-file text may be interpreted as arbitrary shell commands or unrestricted executable code.

## Minimum test matrix

1. Canonical JSON key-order differences produce the same digest.
2. Identical parent and candidate are rejected as a no-op.
3. Invalid or non-finite input is rejected.
4. Stale parent digest is rejected.
5. Any required invariant failure rejects the candidate.
6. Missing required invariant or homeostasis measurement is unresolved.
7. Homeostasis bound violation rejects even when fitness improves.
8. Missing or incompatible evaluator/policy/baseline is unresolved.
9. A fitness regression is rejected.
10. Improvement below the configured threshold is rejected.
11. Improvement meeting the threshold is accepted only when all other checks pass.
12. Rejected and unresolved evaluations leave accepted state unchanged.
13. Evaluation is deterministic for identical inputs and versioned policy.
14. Receipt fields bind the exact parent and candidate digests.
15. Evaluation alone does not write repository files or create a commit.

## Implementation sequence

1. Add typed decision/result structures and stable reason codes.
2. Add pure evaluator with injected, versioned policy/evaluator; no default fitness formula.
3. Add deterministic unit tests for the matrix above.
4. Integrate a homeostasis policy only after its metrics and bounds are explicitly defined.
5. Connect evaluation to the existing sandbox without granting automatic commit authority.
6. Add durable lineage and recovery tests.
7. Verify through CI on an exact commit SHA; separately verify runtime and persistence.

## Evidence status

This document specifies intended behavior. It does not establish that any of the above is implemented, reachable, runtime-tested, persisted, audited, or CI-proven.
