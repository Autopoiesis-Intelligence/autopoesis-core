"""Run bounded tasks and inspect the repository for development opportunities."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autopoesis.core import EvolutionError, digest_state, evolve
from autopoesis.task_queue import record_outcome_file, update_queue_file
from autopoesis.executor import apply_patch_to_sandbox, prepare_patch_artifact
from autopoesis.viability import MetricBound, ViabilityPolicy, evaluate_viability
from autopoesis.evaluation import EvaluationPolicy, evaluate_transition
from autopoesis.receipt_store import append_evaluation_receipt, append_record, load_journal


ROOT = Path(__file__).resolve().parent
IGNORED_PARTS = {".git", "__pycache__", ".venv", "venv"}


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
        "deterministic_digest": digest_state(candidate) == digest_state({"label": "next", "counter": 2}),
        "meaningful_transition_accepted": transition["accepted"],
        "noop_rejected": noop_rejected,
        "state_digest": transition["state_digest"],
    }




def verify_viability_gate() -> dict[str, Any]:
    """Exercise a bounded viability decision; this is not fitness or commit authority."""
    policy = ViabilityPolicy(
        policy_id="runner-smoke-envelope",
        policy_version="1",
        metrics=(
            MetricBound("errors", "validation-errors", "1", "count", minimum=0, maximum=2),
            MetricBound("memory_mb", "memory-footprint", "1", "MB", maximum=256),
        ),
    )

    def measure(state: dict[str, Any], metric: MetricBound) -> float:
        return float(state[metric.name])

    parent = {"errors": 3, "memory_mb": 128}
    viable_candidate = {"errors": 1, "memory_mb": 160}
    unsafe_candidate = {"errors": 1, "memory_mb": 300}
    viable = evaluate_viability(parent, viable_candidate, policy=policy, measure=measure)
    unsafe = evaluate_viability(parent, unsafe_candidate, policy=policy, measure=measure)
    if viable["decision"] != "ACCEPTED":
        raise AssertionError(f"Viable candidate was not accepted by viability gate: {viable}")
    if unsafe["decision"] != "REJECTED":
        raise AssertionError(f"Out-of-bounds candidate was not rejected: {unsafe}")
    return {
        "status": "CHECKS_PASSED",
        "viable_candidate_decision": viable["decision"],
        "unsafe_candidate_decision": unsafe["decision"],
        "unsafe_violations": unsafe["violations"],
        "authority_boundary": "viability only; no fitness, execution, or commit permission",
    }



def verify_decision_journal() -> dict[str, Any]:
    """Exercise durable local journal round-trip and tamper detection in a temporary directory."""
    from autopoesis.receipt_store import JournalIntegrityError

    with tempfile.TemporaryDirectory(prefix="autopoesis-journal-check-") as directory:
        path = Path(directory) / "decisions.json"
        first = append_record(path, {
            "receipt_id": "runner-receipt-1",
            "decision": "ACCEPTED",
            "parent_state_digest": digest_state({"state": "parent"}),
            "candidate_state_digest": digest_state({"state": "candidate"}),
            "evaluator_id": "runner-smoke-evaluator",
            "evaluator_version": "1",
            "evidence_scope": "synthetic self-check only",
        })
        second = append_record(path, {
            "receipt_id": "runner-receipt-2",
            "decision": "REJECTED",
            "parent_state_digest": first["record"]["candidate_state_digest"],
            "candidate_state_digest": digest_state({"state": "unsafe"}),
            "evidence_scope": "synthetic self-check only",
        })
        loaded = load_journal(path)
        if len(loaded["entries"]) != 2 or loaded["entries"][-1]["previous_digest"] != first["entry_digest"]:
            raise AssertionError("Journal round-trip or hash-chain verification failed")

        tampered = json.loads(path.read_text(encoding="utf-8"))
        tampered["entries"][0]["record"]["decision"] = "REJECTED"
        path.write_text(json.dumps(tampered), encoding="utf-8")
        try:
            load_journal(path)
        except JournalIntegrityError:
            tampering_detected = True
        else:
            tampering_detected = False
        if not tampering_detected:
            raise AssertionError("Journal failed to detect record tampering")

    return {
        "status": "CHECKS_PASSED",
        "records_round_tripped": 2,
        "hash_chain_verified": True,
        "tampering_detected": tampering_detected,
        "authority_boundary": "integrity check only; not tamper-proof, execution proof, or evaluator authentication",
    }



def verify_evaluation_receipt_persistence() -> dict[str, Any]:
    """Persist and reload a real evaluation receipt from a synthetic test transition."""
    policy = EvaluationPolicy(
        policy_id="journal-integration-smoke",
        policy_version="1",
        evaluator_id="counter-evaluator",
        evaluator_version="1",
        objective_direction="maximize",
    )
    parent = {"score": 1}
    candidate = {"score": 2}
    receipt = evaluate_transition(
        parent,
        candidate,
        expected_parent_digest=digest_state(parent),
        candidate_id="candidate-journal-smoke",
        policy=policy,
        evaluator=lambda state, fixtures: state["score"],
        fixtures={"fixture_set": "synthetic-v1"},
        invariants=(lambda state: state["score"] >= 0,),
        homeostasis_check=lambda before, after, fixtures: after["score"] >= before["score"],
    )
    if receipt.get("decision") != "ACCEPTED":
        raise AssertionError(f"Evaluation receipt was not accepted: {receipt}")

    with tempfile.TemporaryDirectory(prefix="autopoesis-evaluation-journal-") as directory:
        path = Path(directory) / "decisions.json"
        entry = append_evaluation_receipt(path, receipt, receipt_id="evaluation-smoke-1")
        restored = load_journal(path)
        persisted = restored["entries"][0]["record"]
        if persisted != {**receipt, "receipt_id": "evaluation-smoke-1", "receipt_type": "evaluation_transition"}:
            raise AssertionError("Persisted evaluation receipt differs from source receipt")
        if entry["entry_digest"] != restored["entries"][0]["entry_digest"]:
            raise AssertionError("Persisted entry digest mismatch")

    return {
        "status": "CHECKS_PASSED",
        "decision": receipt["decision"],
        "policy_id": receipt["evaluation_policy_id"],
        "evaluator_id": receipt["evaluator_id"],
        "fixtures_digest_present": "fixtures_digest" in receipt,
        "persisted_and_reloaded": True,
        "authority_boundary": "synthetic evaluation evidence only; not production execution or trusted evaluator authentication",
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


def discover_tasks(repository_root: Path) -> dict[str, Any]:
    """Find evidence-backed, low-risk follow-up tasks without modifying files."""
    candidates: list[dict[str, str]] = []
    python_files = sorted(
        path for path in repository_root.rglob("*.py")
        if not any(part in IGNORED_PARTS for part in path.parts)
    )

    for path in python_files:
        relative = path.relative_to(repository_root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue

        if relative.startswith(("autopoesis/", "run_tasks.py")):
            for line_number, line in enumerate(source.splitlines(), start=1):
                marker = next((item for item in ("TODO", "FIXME", "HACK") if item in line), None)
                if marker:
                    candidate = {
                        "type": "proposal",
                        "source": relative,
                        "evidence": f"{marker} marker on line {line_number}",
                        "description": f"Review and resolve the {marker} marker in {relative}:{line_number}.",
                    }
                    candidate["id"] = "DISC-" + digest_state(candidate)[:12]
                    candidates.append(candidate)

        if relative.startswith("autopoesis/") and path.name != "__init__.py":
            expected_test = repository_root / "tests" / f"test_{path.stem}.py"
            if not expected_test.exists():
                candidate = {
                    "type": "proposal",
                    "source": relative,
                    "evidence": f"no conventional test file found at tests/test_{path.stem}.py",
                    "description": f"Add focused tests for {relative}.",
                }
                candidate["id"] = "DISC-" + digest_state(candidate)[:12]
                candidates.append(candidate)

    unique = {item["id"]: item for item in candidates}
    ordered = [unique[key] for key in sorted(unique)]
    return {
        "status": "CANDIDATES_FOUND" if ordered else "NO_CANDIDATES",
        "candidate_count": len(ordered),
        "candidates": ordered,
        "scope": "static Python source inspection only; no code execution or modification",
    }


def execute_task(task: dict[str, Any], queue_path: Path) -> dict[str, Any]:
    task_id = task.get("id")
    task_type = task.get("type")

    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("Each task needs a non-empty string id")

    if task_type == "verify_evolution_cycle":
        result = verify_evolution_cycle()
    elif task_type == "verify_viability_gate":
        result = verify_viability_gate()
    elif task_type == "verify_decision_journal":
        result = verify_decision_journal()
    elif task_type == "verify_evaluation_receipt_persistence":
        result = verify_evaluation_receipt_persistence()
    elif task_type == "proposal":
        description = task.get("description", "")
        if not isinstance(description, str):
            raise ValueError("Task description must be a string")
        result = create_agent_proposal(description)
    elif task_type == "discover_tasks":
        result = discover_tasks(ROOT)
    elif task_type == "queue_discovered_tasks":
        discovery = discover_tasks(ROOT)
        result = update_queue_file(queue_path, discovery["candidates"])
        result["discovery_status"] = discovery["status"]
        result["discovered"] = discovery["candidate_count"]
    elif task_type == "update_task_status":
        target_id = task.get("task_id")
        status = task.get("status")
        note = task.get("note", "")
        if not isinstance(target_id, str) or not isinstance(status, str) or not isinstance(note, str):
            raise ValueError("update_task_status requires string task_id, status, and optional note")
        result = record_outcome_file(queue_path, target_id, status, note)
    elif task_type == "prepare_test_patch":
        result = prepare_patch_artifact(task, ROOT)
    elif task_type == "apply_test_patch_sandbox":
        artifact = prepare_patch_artifact(task, ROOT)
        with tempfile.TemporaryDirectory(prefix="autopoesis-patch-sandbox-") as directory:
            application = apply_patch_to_sandbox(artifact, Path(directory))
        result = {
            "artifact": artifact,
            "sandbox_application": application,
            "sandbox_lifetime": "temporary; removed after the task",
        }
    else:
        raise ValueError(f"Unsupported task type: {task_type!r}")

    return {"id": task_id, "type": task_type, "status": "PASS", "result": result}


def run(tasks_path: Path, results_path: Path, queue_path: Path = Path("TASK_QUEUE.json")) -> int:
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
                output["tasks"].append(execute_task(task, queue_path))
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
    parser.add_argument("--queue", type=Path, default=Path("TASK_QUEUE.json"))
    args = parser.parse_args()
    return run(args.tasks, args.results, args.queue)


if __name__ == "__main__":
    raise SystemExit(main())
