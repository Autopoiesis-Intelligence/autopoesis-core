import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import EvolutionError, digest_state, evolve
from run_tasks import discover_tasks
from autopoesis.task_queue import load_queue, merge_candidates, record_outcome, update_queue_file


ROOT = Path(__file__).resolve().parents[1]


class EvolutionCoreTests(unittest.TestCase):
    def test_digest_is_deterministic_and_key_order_independent(self):
        self.assertEqual(digest_state({"a": 1, "b": 2}), digest_state({"b": 2, "a": 1}))

    def test_meaningful_change_is_accepted(self):
        result = evolve({"value": 1}, {"value": 2})
        self.assertTrue(result["accepted"])
        self.assertEqual(result["state"], {"value": 2})
        self.assertEqual(result["state_digest"], digest_state({"value": 2}))

    def test_noop_is_rejected(self):
        with self.assertRaises(EvolutionError):
            evolve({"value": 1}, {"value": 1})

    def test_non_json_values_are_rejected(self):
        with self.assertRaises(EvolutionError):
            digest_state({"not_json": object()})

    def test_runner_reads_and_writes_specified_files(self):
        with tempfile.TemporaryDirectory() as directory:
            task_file = Path(directory) / "tasks.json"
            result_file = Path(directory) / "output" / "results.json"
            task_file.write_text(json.dumps({
                "version": 1,
                "tasks": [{"id": "test", "type": "verify_evolution_cycle"}],
            }), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "run_tasks.py"),
                    "--tasks", str(task_file),
                    "--results", str(result_file),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertEqual(result["tasks"][0]["status"], "PASS")


    def test_discovery_finds_actionable_source_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "autopoesis" / "example.py"
            source.parent.mkdir(parents=True)
            source.write_text("# TODO: replace placeholder\\n", encoding="utf-8")
            result = discover_tasks(root)
            self.assertEqual(result["status"], "CANDIDATES_FOUND")
            self.assertGreaterEqual(result["candidate_count"], 2)
            self.assertTrue(any("TODO marker" in item["evidence"] for item in result["candidates"]))
            self.assertTrue(any("test_example.py" in item["evidence"] for item in result["candidates"]))

    def test_discovery_reports_empty_scan_without_mutating_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "autopoesis").mkdir()
            (root / "tests").mkdir()
            result = discover_tasks(root)
            self.assertEqual(result["status"], "NO_CANDIDATES")
            self.assertEqual(result["candidate_count"], 0)


    def test_queue_merge_is_idempotent_and_preserves_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            candidate = {
                "id": "DISC-123",
                "type": "proposal",
                "source": "autopoesis/example.py",
                "evidence": "missing focused test",
                "description": "Add focused tests.",
            }
            first = update_queue_file(path, [candidate])
            self.assertEqual(first["added"], 1)
            self.assertEqual(first["total"], 1)
            queue = load_queue(path)
            queue = record_outcome(queue, "DISC-123", "SELECTED", "highest-value candidate")
            path.write_text(json.dumps(queue), encoding="utf-8")

            second = update_queue_file(path, [candidate])
            self.assertEqual(second["added"], 0)
            reloaded = load_queue(path)
            self.assertEqual(reloaded["items"][0]["status"], "SELECTED")
            self.assertEqual(len(reloaded["history"]), 2)

    def test_queue_rejects_duplicate_ids_in_existing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            path.write_text(json.dumps({
                "version": 1,
                "items": [
                    {"id": "DUP", "status": "OPEN"},
                    {"id": "DUP", "status": "OPEN"},
                ],
                "history": [],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_queue(path)


if __name__ == "__main__":
    unittest.main()
