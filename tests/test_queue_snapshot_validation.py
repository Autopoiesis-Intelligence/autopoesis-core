"""Negative-path and multi-run regression tests for persisted queue snapshots."""

import json
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import EvolutionError
from autopoesis.task_queue import load_queue, update_queue_file
from run_tasks import run


class QueueSnapshotValidationTests(unittest.TestCase):
    def test_corrupt_json_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "TASK_QUEUE.json"
            snapshot.write_text('{"version": 1, "items": [', encoding="utf-8")

            with self.assertRaises(EvolutionError):
                load_queue(snapshot)

    def test_unsupported_snapshot_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "TASK_QUEUE.json"
            snapshot.write_text(json.dumps({
                "version": 999,
                "items": [],
                "history": [],
            }), encoding="utf-8")

            with self.assertRaises(EvolutionError):
                load_queue(snapshot)

    def test_invalid_task_status_in_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "TASK_QUEUE.json"
            snapshot.write_text(json.dumps({
                "version": 1,
                "items": [{"id": "TASK-1", "status": "UNKNOWN"}],
                "history": [],
            }), encoding="utf-8")

            with self.assertRaises(EvolutionError):
                load_queue(snapshot)

    def test_missing_snapshot_loads_as_empty_queue_at_loader_boundary(self):
        # The CI workflow separately checks is_file() before calling load_queue().
        # This documents why that workflow guard is required: the general-purpose
        # loader intentionally treats a missing local queue as an empty queue.
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "missing-TASK_QUEUE.json"

            self.assertEqual(
                load_queue(snapshot),
                {"version": 1, "items": [], "history": []},
            )

    def test_status_and_history_survive_two_runner_invocations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue_path = root / "TASK_QUEUE.json"
            tasks_path = root / "TASKS.json"
            results_path = root / "RESULTS.json"
            candidate = {
                "id": "PERSIST-STATUS-001",
                "type": "proposal",
                "source": "tests/example.py",
                "evidence": "multi-run persistence regression",
                "description": "Keep this task status and history across runs.",
            }
            update_queue_file(queue_path, [candidate])

            tasks_path.write_text(json.dumps({"tasks": [{
                "id": "set-status",
                "type": "update_task_status",
                "task_id": candidate["id"],
                "status": "DONE",
                "note": "first invocation",
            }]}), encoding="utf-8")
            self.assertEqual(run(tasks_path, results_path, queue_path), 0)
            after_first_run = load_queue(queue_path)
            prior_history = list(after_first_run["history"])
            self.assertEqual(after_first_run["items"][0]["status"], "DONE")

            tasks_path.write_text(json.dumps({"tasks": [{
                "id": "merge-discovery",
                "type": "queue_discovered_tasks",
            }]}), encoding="utf-8")
            self.assertEqual(run(tasks_path, results_path, queue_path), 0)
            after_second_run = load_queue(queue_path)

            persisted_item = next(
                item for item in after_second_run["items"]
                if item["id"] == candidate["id"]
            )
            self.assertEqual(persisted_item["status"], "DONE")
            self.assertEqual(
                [event for event in after_second_run["history"] if event in prior_history],
                prior_history,
            )
            self.assertGreaterEqual(len(after_second_run["history"]), len(prior_history))


if __name__ == "__main__":
    unittest.main()
