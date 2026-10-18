"""Minimal file-driven evolution core."""

from .core import EvolutionError, digest_state, evolve
from .evaluation import EvaluationPolicy, evaluate_transition

__all__ = [
    "EvolutionError",
    "EvaluationPolicy",
    "digest_state",
    "evaluate_transition",
    "evolve",
]
