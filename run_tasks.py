"""Run a bounded set of tasks from JSON files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autopoesis.core import EvolutionError, digest_state, evolve


def verify_evolution_cycle() -> dict[str, Any]:
    current = {"counter": 1, "label": "start"}
    candidate = {"counter": 2, "label": "next"}
    transition = evolve(current, candidate)

    if transition["state_digest"] != digest_state(candidate):
        raise AssertionError("Candidate digest mismatch")

    try:
        evolve(candidate, candidate)
    except EvolutionError:
        noop_rejected = True
    else:
        noop_rejected = False

    if not noop_rejected:
        raise AssertionError("No-op transition was not rejected")

    return {
        "deterministic_digest": digest_state(candidate) == digest_state(candidate),
        "meaningful_transition_accepted": transition["accepted"],
        "noop_rejected": noop_rejected,
        "state_digest": transition["state_digest"],
    }


def create_agent_proposal(description: str) -> dict[str, Any]:
    return {
        "status": "PROPOSAL_ONLY",
        "description": description,
        "proposed_interface": {
            "input": "task object and current repository snapshot",
            "output": "patch files plus a machine-readable test report",
            "boundary": "no arbitrary task-provided shell execution",
        },
        "note": (
            "This runner does not generate code. A separate code-writing agent "
            "must be connected to implement this proposal."
        ),
    }


def execute_task(task: dict[str, Any]) -> dict[str, Any]:
    task_id = task.get("id")
    task_type = task.get("type")

    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("Each task needs a non-empty string id")

    if task_type == "verify_evolution_cycle":
        result = verify_evolution_cycle()
    elif task_type == "proposal":
        description = task.get("description", "")
        if not isinstance(description, str):
            raise ValueError("Task description must be a string")
        result = create_agent_proposal(description)
    else:
        raise ValueError(f"Unsupported task type: {task_type!r}")

    return {"id": task_id, "type": task_type, "status": "PASS", "result": result}


def run(tasks_path: Path, results_path: Path) -> int:
    timestamp = datetime.now(timezone.utc).isoformat()
    output: dict[str, Any] = {
        "version": 1,
        "run_at": timestamp,
        "tasks": [],
    }

    try:
        document = json.loads(tasks_path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not isinstance(document.get("tasks"), list):
            raise ValueError("Task file must contain a 'tasks' array")
        seen_ids: set[str] = set()
        for task in document["tasks"]:
            if not isinstance(task, dict):
                raise ValueError("Each task must be a JSON object")
            task_id = task.get("id")
            if isinstance(task_id, str) and task_id in seen_ids:
                raise ValueError(f"Duplicate task id: {task_id}")
            if isinstance(task_id, str):
                seen_ids.add(task_id)
            try:
                output["tasks"].append(execute_task(task))
            except Exception as exc:
                output["tasks"].append({
                    "id": task_id,
                    "type": task.get("type"),
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                })
    except Exception as exc:
        output["error"] = f"{type(exc).__name__}: {exc}"
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return 1

    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 1 if any(item["status"] == "FAIL" for item in output["tasks"]) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=Path("TASKS.json"))
    parser.add_argument("--results", type=Path, default=Path("RESULTS.json"))
    args = parser.parse_args()
    return run(args.tasks, args.results)


if __name__ == "__main__":
    raise SystemExit(main())
