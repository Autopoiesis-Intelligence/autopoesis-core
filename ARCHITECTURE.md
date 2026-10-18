# Autopoiesis Core — Architecture Baseline

**Status:** DESIGN BASELINE  
**Implementation status:** Not established by this document  
**Scope:** Clean-slate architecture for a minimal, deterministic, self-evolving core

## 1. Purpose and restart rationale

Autopoiesis Core is intended to be a self-maintaining and adaptive cognitive architecture whose structure can change in response to interaction with its environment.

The restart separates the new minimal core from accumulated changes and technical debt in earlier implementations. This document records design intent; it is not evidence that any mechanism is implemented, reachable, or runtime-proven.

## 2. Core model and open questions

The intended system works with a state and its relations, written as **Ψ = (X, R)**. The audit uses **X/R** to describe a balance between responsiveness/adaptation and resistance/entropy. Before this becomes an operational control signal, the project must define:
- the exact meaning, units, and calculation of X and R;
- the source and sampling interval of each measurement;
- acceptable operating bounds and how those bounds are validated;
- behavior when measurements are missing, stale, noisy, or contradictory;
- deterministic tests for stability, oscillation, and recovery.

Until those definitions exist, X/R is a hypothesis and must not be treated as a measured runtime guarantee.

## 3. Architectural risks

| Area | Intended advantage | Risk requiring controls |
|---|---|---|
| Adaptation | Respond to changing conditions | Mutation chains make failures difficult to reproduce |
| Autonomy | Reduce repeated manual changes | Positive feedback, runaway loops, or unbounded work |
| Synthesis | Explore non-obvious candidate strategies | Decisions become difficult to explain |
| Entropy management | Detect and retire degraded relations | Incorrect cleanup can remove useful structure |
| Structural coupling | Interact with varied external systems | Mismatched contracts and units can corrupt interpretation |

## 4. Design principles

### 4.1 Immutable substrate and mutable metasystem

The substrate must contain the minimal state-transition engine, canonical serialization and identity rules, evolution protocol, validation primitives, and safety boundaries. These invariants are not candidates for self-modification.

The dynamic layer may propose changes to relations, weights, topology, and bounded adaptive modules, subject to validation and explicit acceptance rules.

### 4.2 Homeostasis before mutation

Before enabling automatic mutation, define and test measurable viability signals, error rates, resource limits, and recovery conditions. When a candidate leaves the permitted operating envelope, reject it or restore the last known-good state. A rollback mechanism itself must be tested.

### 4.3 Candidate → Sandbox → Evaluation → Commit

1. Generate a candidate without changing the active state.
2. Validate its schema, scope, and provenance.
3. Evaluate it in an isolated, resource-bounded environment.
4. Run deterministic regression and safety tests.
5. Accept only when explicit acceptance criteria pass and the target fitness improves without violating invariants.
6. Record the decision and resulting state identity.
7. Otherwise reject the candidate and preserve the prior accepted state.

A generated patch is not an applied patch; a passing synthetic test is not runtime proof; a recorded result is not proof that an authorized production transition occurred.

### 4.4 Evolution lineage and audit trail

Record candidate identity, parent-state digest, candidate digest, evaluator/version, test outcomes, decision, reason, and resulting state digest. History should be append-only at the application level and sufficient to reproduce the evaluation. Wall-clock timestamps are metadata, not a substitute for causal identity.

### 4.5 Structural coupling membrane

External systems provide validated stimuli and receive defined responses through adapters. External input must not directly rewrite the substrate or bypass candidate evaluation. Adapter contracts must explicitly map external DTOs to internal representations and preserve units, provenance, and uncertainty.

## 5. Minimal development roadmap

### Stage 1 — Deterministic substrate
- Canonical state representation and stable digest.
- Explicit transition contract.
- Reject no-op and invalid transitions.
- Unit tests for determinism and immutability.

### Stage 2 — Task intake and discovery
- A repository-local task file is the explicit work queue.
- Discover evidence-backed improvement candidates.
- Assign stable IDs and suppress duplicates.
- Persist lifecycle changes and their history.

### Stage 3 — Homeostasis and rollback
- Define measurable viability signals and operating bounds.
- Test unstable, oscillating, and invalid candidates.
- Demonstrate rollback to a known-good state.

### Stage 4 — Candidate generator
- Generate bounded candidate artifacts from approved task types.
- Do not interpret task descriptions as arbitrary shell or Python commands.
- Validate paths, hashes, syntax, scope, and resource limits.

### Stage 5 — Isolated evaluation
- Apply candidates only in disposable sandboxes.
- Run targeted tests and regression checks without affecting the working tree.
- Produce machine-readable evidence for acceptance or rejection.

### Stage 6 — Governed commit and repeatable evolution
- Require explicit acceptance criteria and an authorized commit boundary.
- Preserve lineage and reproducible evidence.
- Repeat only after the previous cycle has a recorded outcome.

## 6. Required evidence levels

Report each capability separately:

**DESIGN → IMPLEMENTED → REACHABLE → RUNTIME → PERSISTED → AUDITED → CI_PROVEN**

A claim of CI proof must identify the exact commit SHA and CI run. Local tests, synthetic scenarios, a task status, or a generated patch alone do not establish end-to-end runtime evolution.

## 7. Initial implementation boundary

The first version should remain deterministic, standard-library-only where practical, bounded in scope, and easy to inspect. Do not introduce arbitrary task-provided code execution, an implicit clock-driven global operator, or an external selector into the core. Keep code generation, evaluation, acceptance, and commit as distinct stages.

## 8. Naming and repository identity

The repository currently visible to the connected GitHub account is `Autopoiesis-Intelligence/autopoesis-core` (spelled **autopoesis**, missing the second “i” in “autopoiesis”). This document does not rename the repository. Confirm the canonical public name before updating branding, links, package names, or import paths.
