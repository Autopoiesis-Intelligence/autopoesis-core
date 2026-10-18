import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import EvolutionError, digest_state, evolve
from run_tasks import discover_tasks, execute_task, verify_viability_gate
from autopoesis.task_queue import load_queue, record_outcome, record_outcome_file, update_queue_file
from autopoesis.executor import apply_patch_to_sandbox, prepare_patch_artifact, validate_patch_artifact


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


    def test_queue_status_transition_is_persisted_with_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            candidate = {
                "id": "DISC-456",
                "type": "proposal",
                "source": "autopoesis/example.py",
                "evidence": "missing focused test",
                "description": "Add focused tests.",
            }
            update_queue_file(path, [candidate])
            outcome = record_outcome_file(path, "DISC-456", "IN_PROGRESS", "begin bounded work")
            self.assertEqual(outcome["status"], "IN_PROGRESS")
            queue = load_queue(path)
            self.assertEqual(queue["items"][0]["attempts"], 1)
            self.assertEqual(queue["history"][-1]["event"], "STATUS_CHANGED")
            self.assertEqual(queue["history"][-1]["to"], "IN_PROGRESS")


    def test_bounded_writer_prepares_reviewable_patch_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "autopoesis" / "example.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\\n", encoding="utf-8")
            result = prepare_patch_artifact(
                {"id": "DISC-EXAMPLE", "source": "autopoesis/example.py"},
                root,
            )
            self.assertEqual(result["status"], "PATCH_PREPARED")
            self.assertEqual(result["writer_id"], "bounded-test-scaffold-v1")
            self.assertEqual(len(result["files"]), 1)
            self.assertEqual(result["files"][0]["path"], "tests/test_example.py")
            self.assertEqual(source.read_text(encoding="utf-8"), "VALUE = 1\\n")
            self.assertFalse((root / "tests" / "test_example.py").exists())
            self.assertEqual(len(result["files"][0]["sha256"]), 64)
            self.assertEqual(len(result["artifact_sha256"]), 64)

    def test_generated_patch_artifact_is_validated_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "autopoesis" / "example.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\\n", encoding="utf-8")
            artifact = prepare_patch_artifact(
                {"id": "DISC-VALIDATE", "source": "autopoesis/example.py"},
                root,
            )
            self.assertEqual(artifact["validation"]["status"], "VALID")
            self.assertFalse(artifact["validation"]["execution_performed"])
            self.assertEqual(artifact["validation"]["files_checked"], 1)
            self.assertEqual(validate_patch_artifact(artifact)["status"], "VALID")

    def test_patch_artifact_detects_content_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "autopoesis" / "example.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\\n", encoding="utf-8")
            artifact = prepare_patch_artifact(
                {"id": "DISC-TAMPER", "source": "autopoesis/example.py"},
                root,
            )
            artifact["files"][0]["content"] += "# changed\\n"
            with self.assertRaises(ValueError):
                validate_patch_artifact(artifact)

    def test_patch_artifact_rejects_disallowed_output_path(self):
        import hashlib
        from autopoesis.core import canonical_json

        artifact = {
            "status": "PATCH_PREPARED",
            "writer_id": "test-writer",
            "task_id": "DISC-PATH",
            "files": [{
                "path": "autopoesis/unsafe.py",
                "content": "VALUE = 1\\n",
                "sha256": hashlib.sha256(b"VALUE = 1\\n").hexdigest(),
            }],
            "rationale": "test",
        }
        artifact["artifact_sha256"] = hashlib.sha256(
            canonical_json(artifact).encode("utf-8")
        ).hexdigest()
        with self.assertRaises(ValueError):
            validate_patch_artifact(artifact)

    def test_patch_is_applied_only_to_explicit_sandbox(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            source = repository / "autopoesis" / "example.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\\n", encoding="utf-8")
            artifact = prepare_patch_artifact(
                {"id": "DISC-SANDBOX", "source": "autopoesis/example.py"},
                repository,
            )
            sandbox = root / "sandbox"
            result = apply_patch_to_sandbox(artifact, sandbox)
            generated = sandbox / "tests" / "test_example.py"
            self.assertEqual(result["status"], "APPLIED_TO_SANDBOX")
            self.assertTrue(generated.is_file())
            self.assertFalse((repository / "tests" / "test_example.py").exists())
            self.assertFalse(result["repository_modified"])
            self.assertFalse(result["generated_code_executed"])

    def test_patch_application_refuses_to_overwrite_sandbox_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            source = repository / "autopoesis" / "example.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\\n", encoding="utf-8")
            artifact = prepare_patch_artifact(
                {"id": "DISC-NO-OVERWRITE", "source": "autopoesis/example.py"},
                repository,
            )
            sandbox = root / "sandbox"
            target = sandbox / "tests" / "test_example.py"
            target.parent.mkdir(parents=True)
            target.write_text("KEEP = True\\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                apply_patch_to_sandbox(artifact, sandbox)
            self.assertEqual(target.read_text(encoding="utf-8"), "KEEP = True\\n")

    def test_bounded_writer_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "autopoesis" / "example.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare_patch_artifact(
                    {"id": "DISC-EXAMPLE", "source": "../outside.py"},
                    root,
                )


    def test_viability_gate_runner_task_checks_both_outcomes(self):
        result = verify_viability_gate()
        self.assertEqual(result["status"], "CHECKS_PASSED")
        self.assertEqual(result["viable_candidate_decision"], "ACCEPTED")
        self.assertEqual(result["unsafe_candidate_decision"], "REJECTED")
        self.assertIn("no fitness", result["authority_boundary"])

    def test_viability_gate_is_reachable_as_a_file_task(self):
        with tempfile.TemporaryDirectory() as directory:
            queue_path = Path(directory) / "TASK_QUEUE.json"
            result = execute_task(
                {"id": "test-viability", "type": "verify_viability_gate"},
                queue_path,
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["result"]["status"], "CHECKS_PASSED")


if __name__ == "__main__":
    unittest.main()
