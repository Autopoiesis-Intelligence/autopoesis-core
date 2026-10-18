"""Small deterministic state transition primitives."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class EvolutionError(ValueError):
    """Raised when a proposed state transition is invalid."""


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible data deterministically."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvolutionError(f"State must be finite JSON-compatible data: {exc}") from exc


def digest_state(value: Any) -> str:
    """Return a stable SHA-256 digest of canonical JSON state."""
    encoded = canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evolve(current: Any, candidate: Any) -> dict[str, Any]:
    """Accept a changed candidate state; reject no-op transitions."""
    current_digest = digest_state(current)
    candidate_digest = digest_state(candidate)

    if current_digest == candidate_digest:
        raise EvolutionError("No-op evolution is not allowed.")

    return {
        "accepted": True,
        "previous_digest": current_digest,
        "state": candidate,
        "state_digest": candidate_digest,
    }
