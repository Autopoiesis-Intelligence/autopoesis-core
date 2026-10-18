"""Persistent, deterministic task queue primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import EvolutionError, canonical_json


QUEUE_VERSION = 1
QUEUE_STATUSES = {"OPEN", "SELECTED", "IN_PROGRESS", "DONE", "REJECTED"}


def empty_queue() -> dict[str, Any]:
    return {"version": QUEUE_VERSION, "items": [], "history": []}


def load_queue(path: Path) -> dict[str, Any]:
    """Load and validate a queue; a missing file means an empty queue."""
    if not path.exists():
        return empty_queue()
    try:
        queue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvolutionError(f"Cannot read task queue: {exc}") from exc
    if not isinstance(queue, dict) or queue.get("version") != QUEUE_VERSION:
        raise EvolutionError("Unsupported task queue format")
    if not isinstance(queue.get("items"), list) or not isinstance(queue.get("history"), list):
        raise EvolutionError("Task queue must contain items and history arrays")
    seen: set[str] = set()
    for item in queue["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise EvolutionError("Every queued item needs a string id")
        if item["id"] in seen:
            raise EvolutionError(f"Duplicate queued task id: {item['id']}")
        seen.add(item["id"])
        if item.get("status") not in QUEUE_STATUSES:
            raise EvolutionError(f"Invalid status for queued task {item['id']}")
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


def record_outcome(queue: dict[str, Any], task_id: str, status: str, note: str = "") -> dict[str, Any]:
    """Record a bounded lifecycle transition without executing the task."""
    if status not in QUEUE_STATUSES:
        raise EvolutionError(f"Unsupported queue status: {status}")
    updated = json.loads(canonical_json(queue))
    matches = [item for item in updated.get("items", []) if item.get("id") == task_id]
    if len(matches) != 1:
        raise EvolutionError(f"Expected exactly one queued task with id {task_id!r}")
    item = matches[0]
    previous = item["status"]
    item["status"] = status
    if status == "IN_PROGRESS":
        item["attempts"] = int(item.get("attempts", 0)) + 1
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



def _write_queue_atomically(path: Path, queue: dict[str, Any]) -> None:
    """Replace the queue atomically so a process interruption cannot leave partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(queue, indent=2, ensure_ascii=False) + "\\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        finally:
            raise


def update_queue_file(path: Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge discovered candidates into a local persistent JSON queue."""
    current = load_queue(path)
    result = merge_candidates(current, candidates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result["queue"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"added": result["added"], "total": result["total"], "path": path.as_posix()}


def record_outcome_file(path: Path, task_id: str, status: str, note: str = "") -> dict[str, Any]:
    """Persist a status transition and its audit event to the queue file."""
    queue = load_queue(path)
    updated = record_outcome(queue, task_id, status, note)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"task_id": task_id, "status": status, "path": path.as_posix()}


def record_task_result_file(
    path: Path,
    task_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    run_at: str | None = None,
    source_sha: str | None = None,
) -> dict[str, Any]:
    """Append a compact execution-evidence event without changing lifecycle status."""
    if not isinstance(task_id, str) or not task_id.strip():
        raise EvolutionError("Task result needs a non-empty task id")
    if status not in {"PASS", "FAIL"}:
        raise EvolutionError(f"Unsupported execution result status: {status}")
    payload = result if isinstance(result, dict) else {}
    try:
        evidence_json = canonical_json({"task_id": task_id, "status": status, "result": payload})
    except (TypeError, ValueError) as exc:
        raise EvolutionError(f"Execution result is not canonical JSON: {exc}") from exc
    evidence_sha256 = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()
    if source_sha is not None and not re.fullmatch(r"[0-9a-fA-F]{40,64}", source_sha):
        source_sha = None
    timestamp = run_at or datetime.now(timezone.utc).isoformat()
    event = {
        "event": "TASK_RESULT_RECORDED",
        "task_id": task_id,
        "result_status": status,
        "evidence_sha256": evidence_sha256,
        "source_sha": source_sha,
        "failure_reason": payload.get("failure_reason") if isinstance(payload.get("failure_reason"), str) else None,
        "return_code": payload.get("return_code") if isinstance(payload.get("return_code"), int) else None,
        "at": timestamp,
    }
    queue = load_queue(path)
    queue.setdefault("history", []).append(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "task_id": task_id,
        "result_status": status,
        "evidence_sha256": evidence_sha256,
        "source_sha": source_sha,
        "path": path.as_posix(),
    }


def select_next_task_file(path: Path) -> dict[str, Any]:
    """Select one OPEN candidate deterministically; never execute it."""
    queue = load_queue(path)
    candidates = [item for item in queue["items"] if item.get("status") == "OPEN"]
    if not candidates:
        return {"status": "NO_OPEN_TASKS", "task_id": None, "path": path.as_posix()}

    def rank(item: dict[str, Any]) -> tuple[int, int, str]:
        priority = item.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            priority = 0
        attempts = item.get("attempts", 0)
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
            attempts = 0
        return (-priority, attempts, item["id"])

    selected = sorted(candidates, key=rank)[0]
    task_id = selected["id"]
    updated = record_outcome(queue, task_id, "SELECTED", "deterministic queue selection; not executed")
    timestamp = datetime.now(timezone.utc).isoformat()
    selected_item = next(item for item in updated["items"] if item["id"] == task_id)
    priority = selected_item.get("priority", 0)
    if isinstance(priority, bool) or not isinstance(priority, int):
        priority = 0
    attempts = selected_item.get("attempts", 0)
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        attempts = 0
    updated["history"].append({
        "event": "NEXT_TASK_SELECTED",
        "task_id": task_id,
        "selection_rule": "priority_desc_then_attempts_asc_then_task_id_asc",
        "priority": priority,
        "attempts": attempts,
        "execution_started": False,
        "at": timestamp,
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "status": "TASK_SELECTED",
        "task_id": task_id,
        "priority": priority,
        "attempts": attempts,
        "execution_started": False,
        "selection_rule": "priority_desc_then_attempts_asc_then_task_id_asc",
        "path": path.as_posix(),
    }
