"""Negative-path and multi-run regression tests for persisted queue snapshots."""

import json
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import EvolutionError
from autopoesis.queue_snapshot import create_queue_snapshot_manifest, validate_queue_snapshot
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

    def test_generated_test_verification_is_persisted_without_marking_task_done(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue_path = root / "TASK_QUEUE.json"
            tasks_path = root / "TASKS.json"
            results_path = root / "RESULTS.json"
            tasks_path.write_text(json.dumps({"tasks": [{
                "id": "CORE-007-PERSIST",
                "type": "verify_test_patch_sandbox",
                "source": "autopoesis/task_queue.py",
            }]}), encoding="utf-8")

            self.assertEqual(run(tasks_path, results_path, queue_path), 0)
            results = json.loads(results_path.read_text(encoding="utf-8"))
            queue = load_queue(queue_path)

            self.assertEqual(results["tasks"][0]["status"], "PASS")
            self.assertTrue(results["tasks"][0]["result"]["generated_code_executed"])
            self.assertEqual(len(queue["history"]), 1)
            evidence = queue["history"][0]
            self.assertEqual(evidence["event"], "VERIFICATION_RECORDED")
            self.assertEqual(evidence["task_id"], "CORE-007-PERSIST")
            self.assertEqual(evidence["verification_status"], "PASS")
            self.assertEqual(evidence["verification_level"], "GENERATED_TEST_EXECUTION")
            self.assertEqual(len(evidence["artifact_sha256"]), 64)
            self.assertEqual(queue["items"], [])

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


    def _write_bound_snapshot(self, root):
        snapshot = root / "TASK_QUEUE.json"
        manifest_path = root / "QUEUE_SNAPSHOT_MANIFEST.json"
        update_queue_file(snapshot, [{"id": "RESTORE-1", "type": "probe"}])
        expected = {
            "source_run_id": 12345,
            "source_head_sha": "a" * 40,
            "source_repository": "Autopoiesis-Intelligence/autopoesis-core",
        }
        manifest = create_queue_snapshot_manifest(snapshot, **expected)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return snapshot, manifest_path, expected, manifest

    def test_snapshot_manifest_round_trip_binds_queue_to_source(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot, manifest_path, expected, manifest = self._write_bound_snapshot(
                Path(directory)
            )

            result = validate_queue_snapshot(
                snapshot, manifest_path, **expected
            )

            self.assertEqual(result["queue"], load_queue(snapshot))
            self.assertEqual(result["task_queue_sha256"], manifest["task_queue_sha256"])
            self.assertEqual(result["task_queue_size_bytes"], manifest["task_queue_size_bytes"])
            self.assertEqual(len(result["source_manifest_sha256"]), 64)

    def test_snapshot_validation_rejects_wrong_source_run_sha_or_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot, manifest_path, expected, _manifest = self._write_bound_snapshot(
                Path(directory)
            )
            wrong_sources = (
                ({**expected, "source_run_id": 54321}, "run ID"),
                ({**expected, "source_head_sha": "b" * 40}, "SHA"),
                ({**expected, "source_repository": "someone/else"}, "repository"),
            )

            for source, message in wrong_sources:
                with self.subTest(source=source), self.assertRaisesRegex(ValueError, message):
                    validate_queue_snapshot(snapshot, manifest_path, **source)

    def test_snapshot_validation_rejects_tampered_queue_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot, manifest_path, expected, _manifest = self._write_bound_snapshot(
                Path(directory)
            )
            snapshot.write_bytes(snapshot.read_bytes() + b" ")

            with self.assertRaisesRegex(ValueError, "SHA-256"):
                validate_queue_snapshot(snapshot, manifest_path, **expected)

    def test_snapshot_validation_rejects_wrong_queue_size(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot, manifest_path, expected, manifest = self._write_bound_snapshot(
                Path(directory)
            )
            manifest["task_queue_size_bytes"] += 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "size"):
                validate_queue_snapshot(snapshot, manifest_path, **expected)

    def test_snapshot_validation_fails_closed_when_snapshot_or_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, manifest_path, expected, _manifest = self._write_bound_snapshot(root)
            snapshot.unlink()
            with self.assertRaisesRegex(ValueError, "snapshot file is missing"):
                validate_queue_snapshot(snapshot, manifest_path, **expected)

            snapshot, manifest_path, expected, _manifest = self._write_bound_snapshot(root)
            manifest_path.unlink()
            with self.assertRaisesRegex(ValueError, "manifest file is missing"):
                validate_queue_snapshot(snapshot, manifest_path, **expected)


if __name__ == "__main__":
    unittest.main()
