"""Integrity helpers for CI task-queue snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .task_queue import load_queue


_GIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _run_id_text(value: str | int) -> str:
    if isinstance(value, bool):
        raise ValueError("Source run ID must contain decimal digits")
    text = str(value)
    if not text.isdigit():
        raise ValueError("Source run ID must contain decimal digits")
    return text


def create_queue_snapshot_manifest(
    queue_path: Path,
    *,
    source_run_id: str | int,
    source_head_sha: str,
    source_repository: str,
) -> dict[str, Any]:
    """Create metadata binding a queue snapshot to its producing CI run."""
    if not queue_path.is_file():
        raise ValueError("Task queue snapshot file is missing")
    run_id = _run_id_text(source_run_id)
    if not isinstance(source_head_sha, str) or not _GIT_SHA.fullmatch(source_head_sha):
        raise ValueError("Source head SHA must be a 40-character hexadecimal commit hash")
    if not isinstance(source_repository, str) or not source_repository.strip():
        raise ValueError("Source repository must be a non-empty string")

    snapshot = queue_path.read_bytes()
    return {
        "source_run_id": int(run_id),
        "source_head_sha": source_head_sha.lower(),
        "source_repository": source_repository,
        "task_queue_sha256": hashlib.sha256(snapshot).hexdigest(),
        "task_queue_size_bytes": len(snapshot),
    }


def validate_queue_snapshot(
    snapshot_path: Path,
    manifest_path: Path,
    *,
    source_run_id: str | int,
    source_head_sha: str,
    source_repository: str,
) -> dict[str, Any]:
    """Validate snapshot provenance, byte integrity, size, and queue schema."""
    if not snapshot_path.is_file():
        raise ValueError("Queue snapshot file is missing")
    if not manifest_path.is_file():
        raise ValueError("Queue snapshot manifest file is missing")

    expected_run_id = _run_id_text(source_run_id)
    if not isinstance(source_head_sha, str) or not _GIT_SHA.fullmatch(source_head_sha):
        raise ValueError("Verified source head SHA must be a 40-character hexadecimal commit hash")
    if not isinstance(source_repository, str) or not source_repository.strip():
        raise ValueError("Verified source repository must be a non-empty string")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read queue snapshot manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Queue snapshot manifest must be a JSON object")

    if str(manifest.get("source_run_id", "")) != expected_run_id:
        raise ValueError("Snapshot manifest run ID does not match verified source run")
    if manifest.get("source_head_sha") != source_head_sha.lower():
        raise ValueError("Snapshot manifest SHA does not match verified source run SHA")
    if manifest.get("source_repository") != source_repository:
        raise ValueError("Snapshot manifest repository does not match verified source repository")

    snapshot = snapshot_path.read_bytes()
    actual_digest = hashlib.sha256(snapshot).hexdigest()
    expected_digest = manifest.get("task_queue_sha256")
    if not isinstance(expected_digest, str) or not _SHA256.fullmatch(expected_digest):
        raise ValueError("Snapshot manifest has no valid task queue SHA-256")
    if expected_digest != actual_digest:
        raise ValueError("TASK_QUEUE.json SHA-256 does not match source snapshot manifest")

    expected_size = manifest.get("task_queue_size_bytes")
    if type(expected_size) is not int or expected_size < 0:
        raise ValueError("Snapshot manifest has no valid task queue size")
    if expected_size != len(snapshot):
        raise ValueError("TASK_QUEUE.json size does not match source snapshot manifest")

    queue = load_queue(snapshot_path)
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return {
        "queue": queue,
        "source_manifest_sha256": manifest_digest,
        "task_queue_sha256": actual_digest,
        "task_queue_size_bytes": len(snapshot),
    }
