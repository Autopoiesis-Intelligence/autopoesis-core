"""Negative-path regression tests for persisted task queue snapshots."""

import json
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import EvolutionError
from autopoesis.task_queue import load_queue


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


if __name__ == "__main__":
    unittest.main()
