"""Minimal file-driven evolution core."""

from .core import EvolutionError, digest_state, evolve
from .evaluation import EvaluationPolicy, evaluate_transition
from .viability import MetricBound, ViabilityPolicy, evaluate_viability

__all__ = [
    "EvolutionError",
    "EvaluationPolicy",
    "MetricBound",
    "ViabilityPolicy",
    "digest_state",
    "evaluate_transition",
    "evaluate_viability",
    "evolve",
]
