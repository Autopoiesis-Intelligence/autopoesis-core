"""Fail-closed specification checks for future candidate execution.

This module does not execute code or establish that isolation controls are real.
A complete policy is only ready for external adapter review; it is not permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_COMMAND_PROFILES = frozenset({"python-unittest-v1"})


@dataclass(frozen=True)
class CandidateExecutionPolicy:
    """Declared requirements for a future execution adapter."""

    command_profile: str
    timeout_seconds: int
    max_output_bytes: int
    network_disabled: bool
    secrets_excluded: bool
    filesystem_isolated: bool
    os_sandbox_enforced: bool


def assess_execution_policy(policy: CandidateExecutionPolicy | None) -> dict[str, Any]:
    """Check policy completeness without running code or granting execution authority.

    Boolean fields are caller declarations, not verified OS facts. Consequently,
    even a complete policy is not an authorization to execute a candidate.
    """
    if not isinstance(policy, CandidateExecutionPolicy):
        return {
            "status": "BLOCKED",
            "missing_requirements": ["execution_policy"],
            "execution_performed": False,
            "execution_authorized": False,
            "reason": "A typed execution policy is required.",
        }

    missing: list[str] = []
    if policy.command_profile not in ALLOWED_COMMAND_PROFILES:
        missing.append("allowlisted_command_profile")
    if isinstance(policy.timeout_seconds, bool) or not isinstance(policy.timeout_seconds, int) or not 1 <= policy.timeout_seconds <= 60:
        missing.append("timeout_seconds_1_to_60")
    if isinstance(policy.max_output_bytes, bool) or not isinstance(policy.max_output_bytes, int) or not 1 <= policy.max_output_bytes <= 1_000_000:
        missing.append("max_output_bytes_1_to_1000000")
    for field in (
        "network_disabled",
        "secrets_excluded",
        "filesystem_isolated",
        "os_sandbox_enforced",
    ):
        if getattr(policy, field) is not True:
            missing.append(field)

    if missing:
        return {
            "status": "BLOCKED",
            "missing_requirements": missing,
            "execution_performed": False,
            "execution_authorized": False,
            "reason": "Execution requirements are incomplete; fail closed.",
        }

    return {
        "status": "POLICY_COMPLETE_NOT_AUTHORIZED",
        "missing_requirements": [],
        "execution_performed": False,
        "execution_authorized": False,
        "reason": (
            "Declared policy is complete, but caller-supplied flags do not prove "
            "OS isolation. A trusted isolation adapter and independent verification are required."
        ),
    }
