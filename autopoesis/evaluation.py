"""Fail-closed evaluation of a proposed state transition.

This module evaluates candidates only. It never commits files or mutates accepted state.
Callback isolation is defensive, not a proof that callbacks are deterministic or trustworthy.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Iterable, Mapping

from .core import EvolutionError, canonical_json, digest_state

Decision = str
Evaluator = Callable[[Any, Mapping[str, Any]], float]
Invariant = Callable[[Any], bool]
HomeostasisCheck = Callable[[Any, Any, Mapping[str, Any]], bool]


@dataclass(frozen=True)
class EvaluationPolicy:
    policy_id: str
    policy_version: str
    evaluator_id: str
    evaluator_version: str
    objective_direction: str
    min_improvement: float = 0.0
    max_state_bytes: int = 1_000_000
    max_state_depth: int = 64

    def validate(self) -> None:
        if not self.policy_id.strip() or not self.policy_version.strip():
            raise ValueError("Policy identity and version are required.")
        if not self.evaluator_id.strip() or not self.evaluator_version.strip():
            raise ValueError("Evaluator identity and version are required.")
        if self.objective_direction not in {"maximize", "minimize"}:
            raise ValueError("objective_direction must be 'maximize' or 'minimize'.")
        if not isfinite(self.min_improvement) or self.min_improvement < 0:
            raise ValueError("min_improvement must be finite and non-negative.")
        if isinstance(self.max_state_bytes, bool) or not isinstance(self.max_state_bytes, int) or self.max_state_bytes < 1:
            raise ValueError("max_state_bytes must be a positive integer.")
        if isinstance(self.max_state_depth, bool) or not isinstance(self.max_state_depth, int) or self.max_state_depth < 1:
            raise ValueError("max_state_depth must be a positive integer.")


def _depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max(
            (max(_depth(key), _depth(item)) for key, item in value.items()),
            default=0,
        )
    if isinstance(value, list):
        return 1 + max((_depth(item) for item in value), default=0)
    return 0


def _receipt(*, candidate_id: str, parent_digest: str | None,
             candidate_digest: str | None, policy: EvaluationPolicy | None,
             decision: Decision, reason: str, **extra: Any) -> dict[str, Any]:
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
    """Compare parent and candidate using fixed fixtures and fail-closed gates.

    Invariant callback: invariant(candidate_copy) -> bool.
    Homeostasis callback: check(parent_copy, candidate_copy, fixtures_copy) -> bool.
    Evaluator callback: evaluator(state_copy, fixtures_copy) -> finite number.
    """
    parent_digest: str | None = None
    candidate_digest: str | None = None
    try:
        parent_json = canonical_json(parent_state)
        candidate_json = canonical_json(candidate_state)
        parent_digest = digest_state(parent_state)
        candidate_digest = digest_state(candidate_state)
    except (EvolutionError, RecursionError):
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="REJECTED", reason="INVALID_STATE")

    if not expected_parent_digest or parent_digest != expected_parent_digest:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="REJECTED", reason="STALE_PARENT")
    if parent_digest == candidate_digest:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="REJECTED", reason="NO_STATE_CHANGE")
    if policy is None or evaluator is None or fixtures is None:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="UNRESOLVED", reason="MISSING_EVALUATION_EVIDENCE")

    try:
        policy.validate()
        fixtures_digest = digest_state(dict(fixtures))
        if max(len(parent_json.encode("utf-8")), len(candidate_json.encode("utf-8"))) > policy.max_state_bytes:
            return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                            candidate_digest=candidate_digest, policy=policy,
                            decision="UNRESOLVED", reason="STATE_SIZE_LIMIT_EXCEEDED")
        if max(_depth(parent_state), _depth(candidate_state)) > policy.max_state_depth:
            return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                            candidate_digest=candidate_digest, policy=policy,
                            decision="UNRESOLVED", reason="STATE_DEPTH_LIMIT_EXCEEDED")
    except (AttributeError, TypeError, ValueError, EvolutionError, RecursionError):
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="UNRESOLVED", reason="INVALID_POLICY_OR_FIXTURES")

    try:
        invariant_list = tuple(invariants)
    except Exception:
        invariant_list = ()
    if not invariant_list:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="UNRESOLVED", reason="INVARIANTS_MISSING")

    invariant_results: list[bool] = []
    try:
        for invariant in invariant_list:
            result = invariant(deepcopy(candidate_state))
            if not isinstance(result, bool):
                return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                                candidate_digest=candidate_digest, policy=policy,
                                decision="UNRESOLVED", reason="INVARIANT_RESULT_MISSING_OR_INVALID",
                                invariant_results=invariant_results)
            invariant_results.append(result)
    except Exception:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="UNRESOLVED", reason="INVARIANT_EVALUATION_ERROR",
                        invariant_results=invariant_results)

    if not all(invariant_results):
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="REJECTED", reason="INVARIANT_VIOLATION",
                        invariant_results=invariant_results)

    if homeostasis_check is None:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="UNRESOLVED", reason="HOMEOSTASIS_CHECK_MISSING",
                        invariant_results=invariant_results)

    try:
        homeostasis_result = homeostasis_check(
            deepcopy(parent_state), deepcopy(candidate_state), deepcopy(dict(fixtures))
        )
    except Exception:
        homeostasis_result = None
    if not isinstance(homeostasis_result, bool):
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="UNRESOLVED", reason="HOMEOSTASIS_RESULT_MISSING_OR_INVALID",
                        invariant_results=invariant_results)
    if not homeostasis_result:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="REJECTED", reason="HOMEOSTASIS_BOUND_VIOLATION",
                        invariant_results=invariant_results, homeostasis_passed=False)

    try:
        baseline = evaluator(deepcopy(parent_state), deepcopy(dict(fixtures)))
        candidate = evaluator(deepcopy(candidate_state), deepcopy(dict(fixtures)))
        if (isinstance(baseline, bool) or isinstance(candidate, bool)
                or not isinstance(baseline, (int, float))
                or not isinstance(candidate, (int, float))
                or not isfinite(float(baseline)) or not isfinite(float(candidate))):
            raise ValueError("Evaluator must return finite numeric measurements.")
    except Exception:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="UNRESOLVED", reason="FITNESS_EVALUATION_ERROR",
                        invariant_results=invariant_results, homeostasis_passed=True)

    if digest_state(parent_state) != parent_digest or digest_state(candidate_state) != candidate_digest:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="UNRESOLVED", reason="INPUT_STATE_MUTATED",
                        invariant_results=invariant_results, homeostasis_passed=True)

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
        "fixtures_digest": fixtures_digest,
    }
    if improvement < policy.min_improvement:
        return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                        candidate_digest=candidate_digest, policy=policy,
                        decision="REJECTED", reason="INSUFFICIENT_IMPROVEMENT", **common)
    return _receipt(candidate_id=candidate_id, parent_digest=parent_digest,
                    candidate_digest=candidate_digest, policy=policy,
                    decision="ACCEPTED", reason="IMPROVEMENT_THRESHOLD_MET", **common)
