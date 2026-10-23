"""Persistent, deterministic task queue primitives."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None

from .core import EvolutionError, canonical_json


QUEUE_VERSION = 1
QUEUE_STATUSES = {"OPEN", "SELECTED", "IN_PROGRESS", "DONE", "REJECTED"}
QUEUE_HISTORY_EVENTS = {"CANDIDATE_ADDED", "STATUS_CHANGED", "VERIFICATION_RECORDED"}
# Governed lifecycle. DONE and REJECTED are terminal. IN_PROGRESS -> OPEN is
# the retry/interruption path; each entry into IN_PROGRESS counts an attempt.
ALLOWED_TRANSITIONS = {
    "OPEN": frozenset({"SELECTED", "REJECTED"}),
    "SELECTED": frozenset({"IN_PROGRESS", "OPEN", "REJECTED"}),
    "IN_PROGRESS": frozenset({"DONE", "OPEN", "REJECTED"}),
    "DONE": frozenset(),
    "REJECTED": frozenset(),
}
MAX_ATTEMPTS = 3


def _write_queue_atomically(path: Path, queue: dict[str, Any]) -> None:
    """Write a complete queue snapshot before atomically replacing the old one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(queue, indent=2, ensure_ascii=False) + "\n"
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = None

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            if mode is not None:
                os.fchmod(stream.fileno(), mode)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


@contextmanager
def queue_write_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive, non-blocking lock for one load-modify-write cycle.

    Atomic replacement alone prevents torn files but not lost updates: two
    writers that load the same snapshot would both succeed and the second
    would silently discard the first. A concurrent writer is rejected
    instead of waiting, so a caller never reports success for an update
    that another writer overwrote. The lock is not reentrant: do not nest
    helpers that take it, even in the same process.
    """
    if fcntl is None:
        raise EvolutionError("Task queue locking is not supported on this platform")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    descriptor = os.open(
        lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise EvolutionError(
                f"Task queue {path.as_posix()} is locked by another writer"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def empty_queue() -> dict[str, Any]:
    return {"version": QUEUE_VERSION, "items": [], "history": []}


def _validate_history(history: list[Any]) -> None:
    """Reject malformed or unsupported queue history records."""
    for index, event in enumerate(history):
        prefix = f"Invalid task queue history entry at index {index}"
        if not isinstance(event, dict):
            raise EvolutionError(f"{prefix}: expected an object")
        event_type = event.get("event")
        if not isinstance(event_type, str) or event_type not in QUEUE_HISTORY_EVENTS:
            raise EvolutionError(f"{prefix}: unsupported event type {event_type!r}")
        task_id = event.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise EvolutionError(f"{prefix}: task_id must be a non-empty string")
        timestamp = event.get("at")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise EvolutionError(f"{prefix}: at must be a non-empty string")
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise EvolutionError(f"{prefix}: at must be an ISO 8601 timestamp") from exc
        if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
            raise EvolutionError(f"{prefix}: at must include a timezone offset")
        if event_type == "STATUS_CHANGED":
            if not isinstance(event.get("from"), str) or event.get("from") not in QUEUE_STATUSES:
                raise EvolutionError(f"{prefix}: invalid source status")
            if not isinstance(event.get("to"), str) or event.get("to") not in QUEUE_STATUSES:
                raise EvolutionError(f"{prefix}: invalid destination status")
            if not isinstance(event.get("note"), str):
                raise EvolutionError(f"{prefix}: note must be a string")
        if event_type == "VERIFICATION_RECORDED":
            verification_status = event.get("verification_status")
            if not isinstance(verification_status, str) or verification_status not in {"PASS", "FAIL"}:
                raise EvolutionError(f"{prefix}: invalid verification status")
            level = event.get("verification_level")
            if not isinstance(level, str) or not level.strip():
                raise EvolutionError(f"{prefix}: verification_level must be a non-empty string")
            artifact_hash = event.get("artifact_sha256")
            if artifact_hash is not None and (
                not isinstance(artifact_hash, str)
                or len(artifact_hash) != 64
                or any(char not in "0123456789abcdef" for char in artifact_hash)
            ):
                raise EvolutionError(f"{prefix}: artifact_sha256 must be a lowercase SHA-256 hex digest")
            if "source" in event and (not isinstance(event["source"], str) or not event["source"].strip()):
                raise EvolutionError(f"{prefix}: source must be a non-empty string")
            if "attempt" in event and (type(event["attempt"]) is not int or event["attempt"] < 1):
                raise EvolutionError(f"{prefix}: attempt must be a positive integer")
            if "revision" in event and not _is_digest(event["revision"]):
                raise EvolutionError(f"{prefix}: revision must be a lowercase SHA-256 hex digest")


def load_queue(path: Path) -> dict[str, Any]:
    """Load and validate a queue; a missing file means an empty queue."""
    try:
        raw_queue = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Only a genuinely absent file represents a first-run empty queue.
        return empty_queue()
    except (OSError, UnicodeError) as exc:
        raise EvolutionError(f"Cannot read task queue: {exc}") from exc

    try:
        queue = json.loads(raw_queue)
    except json.JSONDecodeError as exc:
        raise EvolutionError(f"Cannot read task queue: {exc}") from exc
    if (
        not isinstance(queue, dict)
        or type(queue.get("version")) is not int
        or queue.get("version") != QUEUE_VERSION
    ):
        raise EvolutionError("Unsupported task queue format")
    if not isinstance(queue.get("items"), list) or not isinstance(queue.get("history"), list):
        raise EvolutionError("Task queue must contain items and history arrays")
    seen: set[str] = set()
    for item in queue["items"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"].strip()
        ):
            raise EvolutionError("Every queued item needs a non-empty string id")
        if item["id"] in seen:
            raise EvolutionError(f"Duplicate queued task id: {item['id']}")
        seen.add(item["id"])
        if not isinstance(item.get("status"), str) or item.get("status") not in QUEUE_STATUSES:
            raise EvolutionError(f"Invalid status for queued task {item['id']}")
        attempts = item.get("attempts", 0)
        if type(attempts) is not int or attempts < 0:
            raise EvolutionError(f"Invalid attempts count for queued task {item['id']}")
        if attempts > MAX_ATTEMPTS:
            raise EvolutionError(f"Queued task {item['id']} exceeds the attempt limit of {MAX_ATTEMPTS}")
    _validate_history(queue["history"])

    # The queue snapshot is the current state; its own audit trail must not
    # contradict that state. Histories may omit transitions for legacy items,
    # but when a transition exists, the final recorded destination must match
    # the persisted item status.
    # Every recorded edge must also be one advance_task could have made, so a
    # restored history cannot carry a completion that skipped the PASS gate.
    sources = {item["id"]: item.get("source") for item in queue["items"]}
    latest_status: dict[str, str] = {}
    replayed_attempts: dict[str, int] = {}
    latest_verification: dict[str, str | None] = {}
    for event in queue["history"]:
        task_id = event.get("task_id")
        if event.get("event") == "VERIFICATION_RECORDED":
            # Verification cannot be appended after a terminal transition. The public
            # writer already blocks this; replay must reject contradictory persisted history.
            if latest_status.get(task_id) in {"DONE", "REJECTED"}:
                raise EvolutionError(
                    f"Queue history records verification for terminal task {task_id!r}"
                )
            # The code revision cannot be compared here, because the code may have moved on
            # since completion, but a PASS without one could never have authorized DONE.
            bound = (
                event.get("source") is not None
                and event.get("source") == sources.get(task_id)
                and event.get("attempt") == replayed_attempts.get(task_id)
                and _is_digest(event.get("revision"))
            )
            latest_verification[task_id] = event["verification_status"] if bound else None
            continue
        if event.get("event") != "STATUS_CHANGED":
            continue
        if event["to"] not in ALLOWED_TRANSITIONS.get(event["from"], frozenset()):
            raise EvolutionError(
                f"Queue history has an illegal transition for task {task_id!r}: {event['from']!r} -> {event['to']!r}"
            )
        if event["to"] == "IN_PROGRESS":
            if replayed_attempts.get(task_id, 0) >= MAX_ATTEMPTS:
                raise EvolutionError(
                    f"Queue history starts task {task_id!r} beyond the attempt limit of {MAX_ATTEMPTS}"
                )
            replayed_attempts[task_id] = replayed_attempts.get(task_id, 0) + 1
            latest_verification[task_id] = None
        if event["to"] == "DONE" and latest_verification.get(task_id) != "PASS":
            raise EvolutionError(
                f"Queue history completes task {task_id!r} without a PASS for its source in that attempt"
            )
        previous_destination = latest_status.get(task_id)
        if previous_destination is not None and event["from"] != previous_destination:
            raise EvolutionError(
                f"Queue history transition chain mismatch for task {task_id!r}: "
                f"next transition starts at {event['from']!r}, "
                f"previous transition ended at {previous_destination!r}"
            )
        latest_status[task_id] = event["to"]
    for item in queue["items"]:
        task_id = item["id"]
        if task_id in latest_status and item.get("attempts", 0) != replayed_attempts.get(task_id, 0):
            raise EvolutionError(
                f"Queue attempts/history mismatch for task {task_id!r}: item says {item.get('attempts', 0)}, "
                f"history has {replayed_attempts.get(task_id, 0)} IN_PROGRESS transitions"
            )
        recorded_status = latest_status.get(task_id)
        if recorded_status is not None and recorded_status != item["status"]:
            raise EvolutionError(
                f"Queue status/history mismatch for task {task_id!r}: "
                f"item status is {item['status']!r}, latest history destination is {recorded_status!r}"
            )
    return queue


def merge_candidates(queue: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Add new candidates once; preserve existing statuses and append audit history."""
    # Validate and copy through canonical JSON so callers cannot mutate stored state.
    try:
        merged = json.loads(canonical_json(queue))
    except (TypeError, ValueError) as exc:
        raise EvolutionError(f"Invalid queue data: {exc}") from exc
    if not isinstance(merged, dict) or merged.get("version") != QUEUE_VERSION:
        raise EvolutionError("Unsupported task queue format")
    if not isinstance(merged.get("items"), list) or not isinstance(merged.get("history"), list):
        raise EvolutionError("Task queue must contain items and history arrays")

    known = {item.get("id"): item for item in merged["items"] if isinstance(item, dict)}
    added = 0
    timestamp = datetime.now(timezone.utc).isoformat()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise EvolutionError("Each candidate must be an object")
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise EvolutionError("Each candidate needs a non-empty string id")
        if candidate_id in known:
            continue
        item = {
            **candidate,
            "status": "OPEN",
            "attempts": 0,
            "first_seen": timestamp,
        }
        merged["items"].append(item)
        known[candidate_id] = item
        merged["history"].append({
            "event": "CANDIDATE_ADDED",
            "task_id": candidate_id,
            "at": timestamp,
        })
        added += 1
    merged["items"].sort(key=lambda item: item["id"])
    merged["history"].sort(key=lambda item: (item.get("at", ""), item.get("task_id", ""), item.get("event", "")))
    return {"queue": merged, "added": added, "total": len(merged["items"])}


def _apply_transition(queue: dict[str, Any], task_id: str, status: str, note: str = "") -> dict[str, Any]:
    """Write one status change; private so that every caller goes through advance_task."""
    if not isinstance(task_id, str) or not task_id.strip():
        raise EvolutionError("Task id must be a non-empty string")
    if not isinstance(status, str) or status not in QUEUE_STATUSES:
        raise EvolutionError(f"Unsupported queue status: {status!r}")
    if not isinstance(note, str):
        raise EvolutionError("Transition note must be a string")
    updated = json.loads(canonical_json(queue))
    matches = [item for item in updated.get("items", []) if item.get("id") == task_id]
    if len(matches) != 1:
        raise EvolutionError(f"Expected exactly one queued task with id {task_id!r}")
    item = matches[0]
    previous = item.get("status")
    if not isinstance(previous, str) or previous not in QUEUE_STATUSES:
        raise EvolutionError(f"Invalid status for queued task {task_id!r}")
    attempts = item.get("attempts", 0)
    if type(attempts) is not int or attempts < 0:
        raise EvolutionError(f"Invalid attempts count for queued task {task_id!r}")
    item["status"] = status
    if status == "IN_PROGRESS":
        item["attempts"] = attempts + 1
    timestamp = datetime.now(timezone.utc).isoformat()
    updated.setdefault("history", []).append({
        "event": "STATUS_CHANGED",
        "task_id": task_id,
        "from": previous,
        "to": status,
        "note": note,
        "at": timestamp,
    })
    return updated


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _has_passing_verification(queue: dict[str, Any], item: dict[str, Any], revision: str | None) -> bool:
    """True when the latest verification since the last IN_PROGRESS is a PASS for this source, attempt and revision."""
    source = item.get("source")
    if not isinstance(source, str) or not source.strip() or not _is_digest(revision):
        return False
    latest = None
    for event in queue.get("history", []):
        if event.get("task_id") != item["id"]:
            continue
        if event.get("event") == "STATUS_CHANGED" and event.get("to") == "IN_PROGRESS":
            latest = None
        elif event.get("event") == "VERIFICATION_RECORDED":
            bound = (
                event.get("source") == source
                and event.get("attempt") == item.get("attempts")
                and event.get("revision") == revision
            )
            latest = event.get("verification_status") if bound else None
    return latest == "PASS"


def advance_task(
    queue: dict[str, Any], task_id: str, status: str, note: str = "", *, revision: str | None = None
) -> dict[str, Any]:
    """Apply one governed lifecycle transition; repeating the current status is a no-op.

    DONE needs ``revision``, the digest of the code as it is now; a PASS recorded
    for other code does not count.
    """
    if not isinstance(status, str) or status not in QUEUE_STATUSES:
        raise EvolutionError(f"Unsupported queue status: {status!r}")
    matches = [item for item in queue.get("items", []) if item.get("id") == task_id]
    if len(matches) != 1:
        raise EvolutionError(f"Expected exactly one queued task with id {task_id!r}")
    item = matches[0]
    previous = item.get("status")
    attempts = item.get("attempts", 0)
    if type(attempts) is not int or attempts < 0:
        raise EvolutionError(f"Invalid attempts count for queued task {task_id!r}")
    if previous == status:
        return {"queue": json.loads(canonical_json(queue)), "changed": False}
    if status not in ALLOWED_TRANSITIONS.get(previous, frozenset()):
        raise EvolutionError(f"Illegal transition for task {task_id!r}: {previous!r} -> {status!r}")
    if status == "IN_PROGRESS" and attempts >= MAX_ATTEMPTS:
        raise EvolutionError(f"Task {task_id!r} reached the attempt limit of {MAX_ATTEMPTS}; reject it instead")
    if status == "DONE" and not _has_passing_verification(queue, item, revision):
        raise EvolutionError(
            f"Task {task_id!r} has no PASS verification of its own source at revision {revision!r} "
            "since its latest IN_PROGRESS"
        )
    return {"queue": _apply_transition(queue, task_id, status, note), "changed": True}


def record_verification_file(
    path: Path,
    task_id: str,
    verification_status: str,
    verification_level: str,
    artifact_sha256: str | None = None,
    source: str | None = None,
    attempt: int | None = None,
    revision: str | None = None,
) -> dict[str, Any]:
    """Persist verification evidence.

    Evidence for a queued item must name that item's source and the attempt
    number captured before verification started; it is refused unless that
    exact attempt is still IN_PROGRESS, so a late result cannot count for a retry.
    ``revision`` is the digest of the code that was tested; DONE compares it
    with the code as it is when the task completes.
    """
    if not isinstance(task_id, str) or not task_id.strip():
        raise EvolutionError("Verification task_id must be a non-empty string")
    if not isinstance(verification_status, str) or verification_status not in {"PASS", "FAIL"}:
        raise EvolutionError(f"Unsupported verification status: {verification_status!r}")
    if not isinstance(verification_level, str) or not verification_level.strip():
        raise EvolutionError("Verification level must be a non-empty string")
    if artifact_sha256 is not None and (
        not isinstance(artifact_sha256, str)
        or len(artifact_sha256) != 64
        or any(char not in "0123456789abcdef" for char in artifact_sha256)
    ):
        raise EvolutionError("artifact_sha256 must be a lowercase SHA-256 hex digest")
    if source is not None and (not isinstance(source, str) or not source.strip()):
        raise EvolutionError("Verification source must be a non-empty string")
    if revision is not None and not _is_digest(revision):
        raise EvolutionError("Verification revision must be a lowercase SHA-256 hex digest")
    if attempt is not None and (type(attempt) is not int or attempt < 1):
        raise EvolutionError("Verification attempt must be a positive integer")

    with queue_write_lock(path):
        queue = load_queue(path)
        item = next((entry for entry in queue["items"] if entry["id"] == task_id), None)
        if item is not None:
            expected = item.get("source")
            if not isinstance(expected, str) or not expected.strip():
                raise EvolutionError(f"Queued task {task_id!r} has no source to bind verification to")
            if source != expected:
                raise EvolutionError(
                    f"Verification source {source!r} does not match queued task {task_id!r} source {expected!r}"
                )
            if item.get("status") != "IN_PROGRESS" or attempt != item.get("attempts"):
                raise EvolutionError(
                    f"Verification for attempt {attempt!r} of task {task_id!r} is stale: the task is "
                    f"{item.get('status')} in attempt {item.get('attempts')}"
                )
        event = {
            "event": "VERIFICATION_RECORDED",
            "task_id": task_id,
            "verification_status": verification_status,
            "verification_level": verification_level,
            "artifact_sha256": artifact_sha256,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        if source is not None:
            event["source"] = source
        if item is not None:
            event["attempt"] = attempt
            if revision is not None:
                event["revision"] = revision
        updated = json.loads(canonical_json(queue))
        updated["history"].append(event)
        _write_queue_atomically(path, updated)
    return {"task_id": task_id, "verification_status": verification_status, "path": path.as_posix()}


def current_attempt(path: Path, task_id: str) -> int | None:
    """The attempt number of an IN_PROGRESS queued task, captured before starting its verification.

    None when the task is absent or not IN_PROGRESS; record_verification_file then refuses the evidence.
    """
    queue = load_queue(path)
    item = next((entry for entry in queue["items"] if entry["id"] == task_id), None)
    if item is None or item.get("status") != "IN_PROGRESS":
        return None
    return item["attempts"]


def update_queue_file(path: Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge discovered candidates into a local persistent JSON queue."""
    with queue_write_lock(path):
        current = load_queue(path)
        result = merge_candidates(current, candidates)
        _write_queue_atomically(path, result["queue"])
    return {"added": result["added"], "total": result["total"], "path": path.as_posix()}


def advance_task_file(
    path: Path, task_id: str, status: str, note: str = "", *, revision: str | None = None
) -> dict[str, Any]:
    """Persist a governed lifecycle transition; a no-op leaves the file untouched."""
    with queue_write_lock(path):
        result = advance_task(load_queue(path), task_id, status, note, revision=revision)
        if result["changed"]:
            _write_queue_atomically(path, result["queue"])
    return {"task_id": task_id, "status": status, "changed": result["changed"], "path": path.as_posix()}
