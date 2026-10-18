"""Minimal file-driven evolution core."""

from .core import EvolutionError, digest_state, evolve

__all__ = ["EvolutionError", "digest_state", "evolve"]
