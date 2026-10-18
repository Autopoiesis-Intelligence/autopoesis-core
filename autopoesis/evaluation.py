"""Pure, fail-closed candidate transition evaluation.

Evaluation emits a decision receipt. It never mutates accepted state or commits files.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Iterable, Mapping

from .core import EvolutionError, canonical_json, digest_state


Decision = str
Evaluator = Callable[[Any, Mapping[str, Any]], float]
Invariant = Callable[[Any], bool]
HomeostasisCheck = Callable[[Any, Mapping[str, Any]], bool]


@dataclass(frozen=True)
class EvaluationPolicy:
    policy_id: str
    policy_version: str
    evaluator_id: str
    evaluator_version: str
    objective_direction: str
    min_improvement: float = 0.0

    def validate(self) -> None:
        if not self.policy_id.strip() or not self.policy_version.strip():
            raise ValueError("Policy identity and version are required.")
        if not self.evaluator_id.strip() or not self.evaluator_version.strip():
            raise ValueError("Evaluator identity and version are required.")
        if self.objective_direction not in {"maximize", "minimize"}:
            raise ValueError("objective_direction must be 'maximize' or 'minimize'.")
        if not isfinite(self.min_improvement) or self.min_improvement < 0:
            raise ValueError("min_improvement must be finite and non-negative.")


def _receipt(
    *,
    candidate_id: str,
    parent_digest: str | None,
    candidate_digest: str | None,
    policy: EvaluationPolicy | None,
    decision: Decision,
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "candidate_id": candidate_id,
        "parent_state_digest": parent_digest,
        "candidate_state_digest": candidate_digest,
        "evaluation_policy_id": policy.policy_id if policy else None,
        "evaluation_policy_version": policy.policy_version if policy else None,
        "evaluator_id": policy.evaluator_id if policy else None,
        "evaluator_version": policy.evaluator_version if policy else None,
        "decision": decision,
        "reason": reason,
    }
    receipt.update(extra)
    return receipt


def evaluate_transition(
    parent_state: Any,
    candidate_state: Any,
    *,
    expected_parent_digest: str,
    candidate_id: str,
    policy: EvaluationPolicy | None,
    evaluator: Evaluator | None,
    fixtures: Mapping[str, Any] | None,
    invariants: Iterable[Invariant] = (),
    homeostasis_check: HomeostasisCheck | None = None,
) -> dict[str, Any]:
    """Evaluate a candidate deterministically; fail closed when evidence is missing.

    Evaluator and check functions are injected by the caller and must be pure,
    deterministic, versioned by policy, and use the same fixtures for both states.
    """
    parent_digest: str | None = None
    candidate_digest: str | None = None
    try:
        # Canonicalization validates JSON compatibility and rejects NaN/Infinity.
        canonical_json(parent_state)
        canonical_json(candidate_state)
        parent_digest = digest_state(parent_state)
        candidate_digest = digest_state(candidate_state)
    except EvolutionError:
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="REJECTED",
            reason="INVALID_STATE",
        )

    if not expected_parent_digest or parent_digest != expected_parent_digest:
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="REJECTED",
            reason="STALE_PARENT",
        )

    if parent_digest == candidate_digest:
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="REJECTED",
            reason="NO_STATE_CHANGE",
        )

    if policy is None or evaluator is None or fixtures is None:
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="UNRESOLVED",
            reason="MISSING_EVALUATION_EVIDENCE",
        )

    try:
        policy.validate()
    except (AttributeError, TypeError, ValueError):
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="UNRESOLVED",
            reason="INVALID_EVALUATION_POLICY",
        )

    invariant_results: list[bool] = []
    try:
        for invariant in invariants:
            result = invariant(candidate_state)
            if not isinstance(result, bool):
                return _receipt(
                    candidate_id=candidate_id,
                    parent_digest=parent_digest,
                    candidate_digest=candidate_digest,
                    policy=policy,
                    decision="UNRESOLVED",
                    reason="INVARIANT_RESULT_MISSING_OR_INVALID",
                    invariant_results=invariant_results,
                )
            invariant_results.append(result)
    except Exception:
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="UNRESOLVED",
            reason="INVARIANT_EVALUATION_ERROR",
            invariant_results=invariant_results,
        )

    if not all(invariant_results):
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="REJECTED",
            reason="INVARIANT_VIOLATION",
            invariant_results=invariant_results,
        )

    if homeostasis_check is None:
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="UNRESOLVED",
            reason="HOMEOSTASIS_CHECK_MISSING",
            invariant_results=invariant_results,
        )

    try:
        homeostasis_result = homeostasis_check(candidate_state, fixtures)
    except Exception:
        homeostasis_result = None

    if not isinstance(homeostasis_result, bool):
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="UNRESOLVED",
            reason="HOMEOSTASIS_RESULT_MISSING_OR_INVALID",
            invariant_results=invariant_results,
        )
    if not homeostasis_result:
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="REJECTED",
            reason="HOMEOSTASIS_BOUND_VIOLATION",
            invariant_results=invariant_results,
            homeostasis_passed=False,
        )

    try:
        baseline = evaluator(parent_state, fixtures)
        candidate = evaluator(candidate_state, fixtures)
        if (
            isinstance(baseline, bool)
            or isinstance(candidate, bool)
            or not isinstance(baseline, (int, float))
            or not isinstance(candidate, (int, float))
            or not isfinite(float(baseline))
            or not isfinite(float(candidate))
        ):
            raise ValueError("Evaluator must return finite numeric measurements.")
    except Exception:
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="UNRESOLVED",
            reason="FITNESS_EVALUATION_ERROR",
            invariant_results=invariant_results,
            homeostasis_passed=True,
        )

    delta = float(candidate) - float(baseline)
    improvement = delta if policy.objective_direction == "maximize" else -delta
    common = {
        "baseline_measurement": float(baseline),
        "candidate_measurement": float(candidate),
        "objective_direction": policy.objective_direction,
        "delta": delta,
        "improvement": improvement,
        "minimum_improvement": float(policy.min_improvement),
        "invariant_results": invariant_results,
        "homeostasis_passed": True,
        "fixtures_digest": digest_state(dict(fixtures)),
    }
    if improvement < policy.min_improvement:
        return _receipt(
            candidate_id=candidate_id,
            parent_digest=parent_digest,
            candidate_digest=candidate_digest,
            policy=policy,
            decision="REJECTED",
            reason="INSUFFICIENT_IMPROVEMENT",
            **common,
        )

    return _receipt(
        candidate_id=candidate_id,
        parent_digest=parent_digest,
        candidate_digest=candidate_digest,
        policy=policy,
        decision="ACCEPTED",
        reason="IMPROVEMENT_THRESHOLD_MET",
        **common,
    )
