"""Minimal file-driven evolution core."""

from .core import EvolutionError, digest_state, evolve
from .evaluation import EvaluationPolicy, evaluate_transition
from .viability import MetricBound, ViabilityPolicy, evaluate_viability
from .receipt_store import JournalIntegrityError, append_evaluation_receipt, append_record, load_journal
from .execution_policy import CandidateExecutionPolicy, assess_execution_policy, inspect_host_isolation_capabilities

__all__ = [
    "EvolutionError",
    "EvaluationPolicy",
    "CandidateExecutionPolicy",
    "assess_execution_policy",
    "inspect_host_isolation_capabilities",
    "MetricBound",
    "JournalIntegrityError",
    "append_evaluation_receipt",
    "append_record",
    "load_journal",
    "ViabilityPolicy",
    "digest_state",
    "evaluate_transition",
    "evaluate_viability",
    "evolve",
]
