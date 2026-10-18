"""Persistent, deterministic task queue primitives."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import EvolutionError, canonical_json


QUEUE_VERSION = 1
QUEUE_STATUSES = {"OPEN", "SELECTED", "IN_PROGRESS", "DONE", "REJECTED"}
QUEUE_HISTORY_EVENTS = {"CANDIDATE_ADDED", "STATUS_CHANGED"}


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
        if event_type == "STATUS_CHANGED":
            if not isinstance(event.get("from"), str) or event.get("from") not in QUEUE_STATUSES:
                raise EvolutionError(f"{prefix}: invalid source status")
            if not isinstance(event.get("to"), str) or event.get("to") not in QUEUE_STATUSES:
                raise EvolutionError(f"{prefix}: invalid destination status")
            if not isinstance(event.get("note"), str):
                raise EvolutionError(f"{prefix}: note must be a string")


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
        if not isinstance(item.get("status"), str) or item.get("status") not in QUEUE_STATUSES:
            raise EvolutionError(f"Invalid status for queued task {item['id']}")
    _validate_history(queue["history"])
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
