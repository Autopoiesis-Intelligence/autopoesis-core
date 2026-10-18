"""Explicit, domain-neutral viability bounds for state transitions.

This module intentionally defines no universal X/R or entropy formula. A caller
must supply named metrics with units and explicit bounds. Viability is a safety
gate, not a fitness score and not execution/commit authority.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable

from .core import EvolutionError, digest_state


@dataclass(frozen=True)
class MetricBound:
    name: str
    metric_id: str
    metric_version: str
    unit: str
    minimum: float | None = None
    maximum: float | None = None

    def validate(self) -> None:
        if not self.name.strip() or not self.metric_id.strip() or not self.metric_version.strip():
            raise ValueError("Metric name, ID, and version are required.")
        if not self.unit.strip():
            raise ValueError("Metric unit is required; use 'unitless' when appropriate.")
        if self.minimum is None and self.maximum is None:
            raise ValueError("At least one viability bound is required.")
        for value in (self.minimum, self.maximum):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value))):
                raise ValueError("Viability bounds must be finite numeric values.")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Minimum viability bound cannot exceed maximum.")


@dataclass(frozen=True)
class ViabilityPolicy:
    policy_id: str
    policy_version: str
    metrics: tuple[MetricBound, ...]

    def validate(self) -> None:
        if not self.policy_id.strip() or not self.policy_version.strip():
            raise ValueError("Viability policy ID and version are required.")
        if not self.metrics:
            raise ValueError("At least one viability metric is required.")
        names: set[str] = set()
        for metric in self.metrics:
            metric.validate()
            if metric.name in names:
                raise ValueError(f"Duplicate viability metric name: {metric.name}")
            names.add(metric.name)


MetricMeasurer = Callable[[Any, MetricBound], float]


def _inside_bounds(value: float, metric: MetricBound) -> bool:
    return (
        (metric.minimum is None or value >= metric.minimum)
        and (metric.maximum is None or value <= metric.maximum)
    )


def evaluate_viability(
    parent_state: Any,
    candidate_state: Any,
    *,
    policy: ViabilityPolicy | None,
    measure: MetricMeasurer | None,
) -> dict[str, Any]:
    """Measure parent and candidate against explicit viability bounds.

    Missing policy/metrics, invalid measurements, and callback errors are
    UNRESOLVED. Candidate bound violations are REJECTED. This function never
    mutates accepted state, executes code, or commits changes.
    """
    try:
        parent_digest = digest_state(parent_state)
        candidate_digest = digest_state(candidate_state)
    except (EvolutionError, RecursionError):
        return {
            "decision": "UNRESOLVED", "reason": "INVALID_STATE",
            "parent_state_digest": None, "candidate_state_digest": None,
        }

    base = {
        "schema_version": 1,
        "parent_state_digest": parent_digest,
        "candidate_state_digest": candidate_digest,
        "viability_policy_id": policy.policy_id if policy else None,
        "viability_policy_version": policy.policy_version if policy else None,
    }
    if policy is None or measure is None:
        return {**base, "decision": "UNRESOLVED", "reason": "VIABILITY_POLICY_OR_MEASURER_MISSING"}
    try:
        policy.validate()
    except (AttributeError, TypeError, ValueError):
        return {**base, "decision": "UNRESOLVED", "reason": "INVALID_VIABILITY_POLICY"}

    measurements: dict[str, dict[str, Any]] = {}
    try:
        for metric in policy.metrics:
            parent_value = measure(deepcopy(parent_state), metric)
            candidate_value = measure(deepcopy(candidate_state), metric)
            for value in (parent_value, candidate_value):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
                    raise ValueError(f"Metric {metric.name} did not produce a finite numeric value.")
            parent_number, candidate_number = float(parent_value), float(candidate_value)
            measurements[metric.name] = {
                "metric_id": metric.metric_id,
                "metric_version": metric.metric_version,
                "unit": metric.unit,
                "minimum": metric.minimum,
                "maximum": metric.maximum,
                "parent_value": parent_number,
                "candidate_value": candidate_number,
                "parent_within_bounds": _inside_bounds(parent_number, metric),
                "candidate_within_bounds": _inside_bounds(candidate_number, metric),
            }
    except Exception:
        return {**base, "decision": "UNRESOLVED", "reason": "VIABILITY_MEASUREMENT_ERROR"}

    if digest_state(parent_state) != parent_digest or digest_state(candidate_state) != candidate_digest:
        return {**base, "decision": "UNRESOLVED", "reason": "INPUT_STATE_MUTATED",
                "measurements": measurements}

    violations = [
        name for name, result in measurements.items()
        if not result["candidate_within_bounds"]
    ]
    return {
        **base,
        "decision": "REJECTED" if violations else "ACCEPTED",
        "reason": "VIABILITY_BOUND_VIOLATION" if violations else "VIABILITY_BOUNDS_SATISFIED",
        "measurements": measurements,
        "violations": violations,
    }
