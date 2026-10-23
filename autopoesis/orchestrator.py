"""A10: one bounded, unattended cycle over the task queue.

recover expired leases -> select one task the runner can execute -> IN_PROGRESS
-> run its allowlisted handler -> record verification -> DONE, OPEN or REJECTED.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .core import EvolutionError
from .executor import source_tree_digest, verify_test_patch_in_sandbox
from .task_queue import (
    MAX_ATTEMPTS,
    advance_task_file,
    current_attempt,
    load_queue,
    record_verification_file,
    recover_expired_leases_file,
    select_next_task_file,
)

Handler = Callable[[dict[str, Any], Path], dict[str, Any]]


def verify_test_scaffold(item: dict[str, Any], repository_root: Path) -> dict[str, Any]:
    """Run the bounded generated import test for the item's source in a disposable sandbox."""
    result = verify_test_patch_in_sandbox({"id": item["id"], "source": item["source"]}, repository_root)
    return {
        "verification_status": result["verification_status"],
        "verification_level": "GENERATED_TEST_EXECUTION",
        "artifact_sha256": result.get("artifact_sha256"),
        "revision": result.get("source_tree_sha256"),
        "detail": result.get("failure_reason"),
    }


# The allowlist: an item runs only if its type is a key here. Task data never names code to run.
HANDLERS: dict[str, Handler] = {"verify_test_scaffold": verify_test_scaffold}
DEFAULT_BUDGET_SECONDS = 600
LOCK_RETRIES = 50
LOCK_RETRY_SECONDS = 0.1


def _when_unlocked(call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Queue writers fail fast on a held lock; a runner waits briefly instead of dropping its own step."""
    for remaining in range(LOCK_RETRIES, 0, -1):
        try:
            return call(*args, **kwargs)
        except EvolutionError as exc:
            if "locked by another writer" not in str(exc) or remaining == 1:
                raise
            time.sleep(LOCK_RETRY_SECONDS)
    raise AssertionError("unreachable")


def _run_handler(handler: Handler, item: dict[str, Any], root: Path, results: Any) -> None:
    try:
        results.put(handler(item, root))
    except Exception as exc:  # A handler failure is the task's outcome, not the runner's crash.
        results.put({"verification_status": "FAIL", "verification_level": "HANDLER_ERROR",
                     "detail": f"{type(exc).__name__}: {exc}"})


def _bounded(handler: Handler, item: dict[str, Any], root: Path, seconds: float) -> dict[str, Any] | None:
    """Run the handler in a child process and kill it at the deadline; None means it ran out of time."""
    context = multiprocessing.get_context("fork")
    results = context.Queue()
    child = context.Process(target=_run_handler, args=(handler, item, root, results), daemon=True)
    child.start()
    child.join(max(seconds, 0))
    if child.is_alive():
        child.kill()
        child.join()
        return None
    if results.empty():
        return {"verification_status": "FAIL", "verification_level": "HANDLER_ERROR",
                "detail": f"handler exited with code {child.exitcode} and no result"}
    return results.get()


def run_cycle(
    queue_path: Path,
    owner: str,
    repository_root: Path,
    *,
    handlers: dict[str, Handler] | None = None,
    disable_path: Path | None = None,
    budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Run at most one task to an outcome; never raises for a task's own failure."""
    handlers = HANDLERS if handlers is None else handlers
    if disable_path is not None and disable_path.exists():
        return {"status": "DISABLED", "reason": f"disable switch present at {disable_path.as_posix()}"}
    started = clock()
    report: dict[str, Any] = {}
    try:
        report["recovered"] = _when_unlocked(recover_expired_leases_file, queue_path)["recovered"]
        selection = _when_unlocked(select_next_task_file, queue_path, owner, types=frozenset(handlers))
        if selection["selected"] is None:
            return {**report, "status": "NO_WORK", "reason": selection["reason"]}

        task_id = selection["selected"]
        token = selection["lease"]["token"]
        report["task_id"] = task_id
        _when_unlocked(advance_task_file, queue_path, task_id, "IN_PROGRESS", f"started by {owner}", token=token)
        attempt = current_attempt(queue_path, task_id)
        item = next(entry for entry in load_queue(queue_path)["items"] if entry["id"] == task_id)
        report["attempt"] = attempt
        outcome = _bounded(handlers[item["type"]], item, repository_root, budget_seconds - (clock() - started))
        if outcome is not None and outcome.get("verification_status") not in {"PASS", "FAIL"}:
            outcome = {"verification_status": "FAIL", "verification_level": "HANDLER_ERROR",
                       "detail": f"handler returned verification_status {outcome.get('verification_status')!r}"}

        if outcome is None or clock() - started > budget_seconds:
            # Evidence that arrives after the budget is not trusted; release the task untouched by it.
            _when_unlocked(advance_task_file, queue_path, task_id, "OPEN",
                           f"time budget of {budget_seconds}s exceeded", token=token)
            return {**report, "status": "TIMED_OUT", "final": "OPEN"}
        report["verification"] = outcome["verification_status"]
        report["detail"] = outcome.get("detail")

        _when_unlocked(
            record_verification_file, queue_path, task_id, outcome["verification_status"],
            outcome.get("verification_level", "UNSPECIFIED"), outcome.get("artifact_sha256"), item["source"],
            attempt, outcome.get("revision"), token,
        )
        if outcome["verification_status"] == "PASS":
            revision = source_tree_digest(repository_root / "autopoesis")
            _when_unlocked(advance_task_file, queue_path, task_id, "DONE", f"verified by {owner}",
                           token=token, revision=revision)
            final = "DONE"
        else:
            final = "REJECTED" if attempt >= MAX_ATTEMPTS else "OPEN"
            _when_unlocked(advance_task_file, queue_path, task_id, final,
                           f"verification failed: {outcome.get('detail')}", token=token)
    except EvolutionError as exc:
        # The queue refused a step (for example a stale lease after recovery); nothing more is written.
        return {**report, "status": "REFUSED", "reason": str(exc)}
    return {**report, "status": "COMPLETED", "final": final}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=Path("TASK_QUEUE.json"))
    parser.add_argument("--owner", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--disable-file", type=Path)
    parser.add_argument("--budget-seconds", type=float, default=DEFAULT_BUDGET_SECONDS)
    args = parser.parse_args()
    result = run_cycle(args.queue, args.owner, args.root.resolve(), disable_path=args.disable_file,
                       budget_seconds=args.budget_seconds)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["status"] == "REFUSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
