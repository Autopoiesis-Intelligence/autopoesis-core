"""Fail-closed specification checks for future candidate execution.

This module does not execute code or establish that isolation controls are real.
A complete policy is only ready for external adapter review; it is not permission.
"""

from __future__ import annotations

from dataclasses import dataclass
import platform
import shutil
import subprocess
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
    if not isinstance(policy.command_profile, str) or policy.command_profile not in ALLOWED_COMMAND_PROFILES:
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



ISOLATION_TOOL_CANDIDATES = (
    "bwrap",
    "firejail",
    "nsjail",
    "docker",
    "podman",
    "unshare",
    "sandbox-exec",
)


def inspect_host_isolation_capabilities() -> dict[str, Any]:
    """Inventory known isolation-tool executables without running them.

    Tool presence does not prove kernel support, permissions, correct configuration,
    or effective isolation. This function never enables candidate execution.
    """
    discovered = {
        name: path
        for name in ISOLATION_TOOL_CANDIDATES
        if (path := shutil.which(name)) is not None
    }
    return {
        "status": "NO_VERIFIED_SANDBOX",
        "platform": platform.system(),
        "os_name": __import__("os").name,
        "python_version": platform.python_version(),
        "discovered_tools": discovered,
        "tool_presence_is_proof": False,
        "execution_authorized": False,
        "execution_performed": False,
        "required_follow_up": (
            "Verify kernel features, user permissions, filesystem and network restrictions, "
            "credential exclusion, and resource limits with dedicated adversarial tests."
        ),
    }


def probe_isolation_runtime(timeout_seconds: int = 3, output_limit: int = 2048) -> dict[str, Any]:
    """Run only fixed, read-only runtime capability probes; never execute candidate code."""
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 5:
        raise ValueError("timeout_seconds must be an integer from 1 to 5")
    if isinstance(output_limit, bool) or not isinstance(output_limit, int) or not 128 <= output_limit <= 4096:
        raise ValueError("output_limit must be an integer from 128 to 4096")

    commands = {
        "docker_daemon": ("docker", "info", "--format", "{{.ServerVersion}}"),
        "podman_runtime": ("podman", "info", "--format", "{{.Host.Security.Rootless}}"),
        "user_namespace": ("unshare", "--user", "--map-root-user", "true"),
    }
    probes: dict[str, Any] = {}
    for name, argv in commands.items():
        executable = shutil.which(argv[0])
        if executable is None:
            probes[name] = {"available": False, "reason": "executable_not_found"}
            continue
        fixed_argv = (executable, *argv[1:])
        try:
            result = subprocess.run(
                fixed_argv,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            )
            stdout = result.stdout[:output_limit]
            stderr = result.stderr[:output_limit]
            probes[name] = {
                "available": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            probes[name] = {
                "available": False,
                "returncode": None,
                "stdout": (exc.stdout or b"").decode("utf-8", "replace")[:output_limit] if isinstance(exc.stdout, bytes) else str(exc.stdout or "")[:output_limit],
                "stderr": (exc.stderr or b"").decode("utf-8", "replace")[:output_limit] if isinstance(exc.stderr, bytes) else str(exc.stderr or "")[:output_limit],
                "timed_out": True,
            }
        except OSError as exc:
            probes[name] = {
                "available": False,
                "returncode": None,
                "stdout": "",
                "stderr": f"{type(exc).__name__}: {exc}"[:output_limit],
                "timed_out": False,
            }

    return {
        "status": "CAPABILITY_PROBE_ONLY",
        "probes": probes,
        "candidate_code_executed": False,
        "execution_authorized": False,
        "sandbox_verified": False,
        "note": "Fixed read-only probes indicate runtime availability only; they do not prove a secure candidate sandbox.",
    }
