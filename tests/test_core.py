import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import EvolutionError, digest_state, evolve
from run_tasks import discover_tasks, execute_selected_task, execute_task
from autopoesis.task_queue import load_queue, record_outcome, record_outcome_file, record_task_result_file, select_next_task_file, update_queue_file
from autopoesis.executor import apply_patch_to_sandbox, prepare_patch_artifact, validate_patch_artifact, verify_test_patch_in_sandbox


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
                    "--queue", str(Path(directory) / "TASK_QUEUE.json"),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertEqual(result["tasks"][0]["status"], "PASS")
            queue = load_queue(Path(directory) / "TASK_QUEUE.json")
            self.assertEqual(queue["history"][-1]["event"], "TASK_RESULT_RECORDED")
            self.assertEqual(queue["history"][-1]["result_status"], "PASS")
            self.assertEqual(len(queue["history"][-1]["evidence_sha256"]), 64)


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


    def test_generated_import_test_executes_in_disposable_package_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "autopoesis"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "example.py").write_text("VALUE = 42\n", encoding="utf-8")
            result = verify_test_patch_in_sandbox(
                {"id": "DISC-VERIFY", "source": "autopoesis/example.py"},
                root,
            )
            self.assertEqual(result["verification_status"], "PASS", result["stdout"] + result["stderr"])
            self.assertEqual(result["return_code"], 0)
            self.assertTrue(result["generated_code_executed"])
            self.assertFalse(result["repository_modified"])
            self.assertIn("Ran 1 test", result["stderr"])
            self.assertFalse((root / "tests" / "test_example.py").exists())

    def test_sandbox_verification_rejects_symlinked_package_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "real_package"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "example.py").write_text("VALUE = 1\\n", encoding="utf-8")
            (root / "autopoesis").symlink_to(package, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlinked source package"):
                verify_test_patch_in_sandbox(
                    {"id": "DISC-SYMLINK", "source": "autopoesis/example.py"},
                    root,
                )


    def test_sandbox_verification_rejects_unbounded_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "autopoesis"
            package.mkdir()
            (package / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_test_patch_in_sandbox(
                    {"id": "DISC-TIMEOUT", "source": "autopoesis/example.py"},
                    root,
                    timeout_seconds=999,
                )


    def test_task_result_history_records_pass_and_fail_without_changing_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [{
                "id": "DISC-RESULT",
                "type": "proposal",
                "source": "autopoesis/example.py",
                "evidence": "test result persistence",
                "description": "Keep lifecycle independent from verification outcome.",
            }])
            record_outcome_file(path, "DISC-RESULT", "SELECTED", "selected for work")
            record_task_result_file(
                path,
                "DISC-RESULT",
                "FAIL",
                {"failure_reason": "TEST_FAILURE", "return_code": 1, "stderr": "private output"},
                run_at="2026-10-18T00:00:00+00:00",
                source_sha="a" * 40,
            )
            queue = load_queue(path)
            item = next(item for item in queue["items"] if item["id"] == "DISC-RESULT")
            event = queue["history"][-1]
            self.assertEqual(item["status"], "SELECTED")
            self.assertEqual(event["event"], "TASK_RESULT_RECORDED")
            self.assertEqual(event["result_status"], "FAIL")
            self.assertEqual(event["failure_reason"], "TEST_FAILURE")
            self.assertEqual(event["return_code"], 1)
            self.assertEqual(event["source_sha"], "a" * 40)
            self.assertEqual(len(event["evidence_sha256"]), 64)
            self.assertNotIn("private output", json.dumps(queue))


    def test_next_task_selection_is_deterministic_and_does_not_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [
                {"id": "DISC-B", "type": "proposal", "source": "b.py", "evidence": "b", "description": "B", "priority": 3},
                {"id": "DISC-A", "type": "proposal", "source": "a.py", "evidence": "a", "description": "A", "priority": 3},
                {"id": "DISC-C", "type": "proposal", "source": "c.py", "evidence": "c", "description": "C", "priority": 9},
            ])
            selected = select_next_task_file(path)
            self.assertEqual(selected["status"], "TASK_SELECTED")
            self.assertEqual(selected["task_id"], "DISC-C")
            self.assertFalse(selected["execution_started"])
            queue = load_queue(path)
            item = next(item for item in queue["items"] if item["id"] == "DISC-C")
            self.assertEqual(item["status"], "SELECTED")
            self.assertEqual(queue["history"][-1]["event"], "NEXT_TASK_SELECTED")
            self.assertFalse(queue["history"][-1]["execution_started"])

            # Once the highest-priority item is no longer OPEN, ties resolve by ID.
            selected_again = select_next_task_file(path)
            self.assertEqual(selected_again["task_id"], "DISC-A")
            self.assertFalse(selected_again["execution_started"])

    def test_next_task_selection_returns_empty_when_no_open_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [
                {"id": "DISC-DONE", "type": "proposal", "source": "d.py", "evidence": "done", "description": "Done"},
            ])
            record_outcome_file(path, "DISC-DONE", "DONE", "already completed")
            result = select_next_task_file(path)
            self.assertEqual(result["status"], "NO_OPEN_TASKS")
            self.assertIsNone(result["task_id"])


    def test_selected_executor_runs_only_allowlisted_proposal_and_does_not_complete_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [{
                "id": "DISC-EXEC",
                "type": "proposal",
                "source": "autopoesis/example.py",
                "evidence": "missing test",
                "description": "Prepare a bounded test proposal.",
            }])
            record_outcome_file(path, "DISC-EXEC", "SELECTED", "chosen by selector")
            result = execute_selected_task({"type": "execute_selected_task"}, path)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["execution_started"])
            self.assertFalse(result["automatic_completion"])
            self.assertEqual(result["lifecycle_status_after_execution"], "IN_PROGRESS")
            queue = load_queue(path)
            item = next(item for item in queue["items"] if item["id"] == "DISC-EXEC")
            self.assertEqual(item["status"], "IN_PROGRESS")
            self.assertEqual(queue["history"][-1]["event"], "TASK_RESULT_RECORDED")
            self.assertEqual(queue["history"][-1]["result_status"], "PASS")

    def test_selected_executor_persists_failure_when_handler_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [{
                "id": "DISC-EXEC-FAIL",
                "type": "prepare_test_patch",
                "source": "autopoesis/does_not_exist.py",
                "evidence": "failure persistence",
                "description": "Must preserve failure evidence.",
            }])
            record_outcome_file(path, "DISC-EXEC-FAIL", "SELECTED", "selected for execution")
            result = execute_selected_task({"type": "execute_selected_task"}, path)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(result["execution_started"])
            self.assertEqual(result["result"]["failure_reason"], "EXECUTION_ERROR")
            queue = load_queue(path)
            item = next(item for item in queue["items"] if item["id"] == "DISC-EXEC-FAIL")
            self.assertEqual(item["status"], "IN_PROGRESS")
            event = queue["history"][-1]
            self.assertEqual(event["event"], "TASK_RESULT_RECORDED")
            self.assertEqual(event["result_status"], "FAIL")
            self.assertEqual(event["failure_reason"], "EXECUTION_ERROR")

    def test_runner_reports_blocked_selected_task_as_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [{
                "id": "DISC-BLOCKED-RUNNER",
                "type": "arbitrary_shell",
                "source": "ignored",
                "evidence": "untrusted task type",
                "description": "Must not execute.",
            }])
            record_outcome_file(path, "DISC-BLOCKED-RUNNER", "SELECTED", "test runner status propagation")
            result = execute_task({"id": "CORE-010", "type": "execute_selected_task"}, path)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["result"]["status"], "BLOCKED")
            self.assertFalse(result["result"]["execution_started"])

    def test_selected_executor_blocks_unsupported_type_without_starting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [{
                "id": "DISC-BLOCKED",
                "type": "arbitrary_shell",
                "source": "ignored",
                "evidence": "untrusted task type",
                "description": "Must not execute.",
            }])
            record_outcome_file(path, "DISC-BLOCKED", "SELECTED", "test selection")
            result = execute_selected_task({"type": "execute_selected_task"}, path)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertFalse(result["execution_started"])
            self.assertEqual(result["reason"], "UNSUPPORTED_SELECTED_TASK_TYPE")
            item = load_queue(path)["items"][0]
            self.assertEqual(item["status"], "SELECTED")

    def test_selected_executor_requires_selected_task(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [{
                "id": "DISC-OPEN",
                "type": "proposal",
                "source": "x.py",
                "evidence": "open",
                "description": "Not selected yet.",
            }])
            with self.assertRaises(ValueError):
                execute_selected_task({"type": "execute_selected_task"}, path)


    def test_queue_select_execute_sandbox_and_reload_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [{
                "id": "CORE-SEQ-M2-ROUNDTRIP",
                "type": "verify_test_patch_sandbox",
                "source": "autopoesis/task_queue.py",
                "evidence": "round-trip integration test",
                "description": "Verify generated import test in disposable package copy.",
                "priority": 7,
            }])

            selected = select_next_task_file(path)
            self.assertEqual(selected["task_id"], "CORE-SEQ-M2-ROUNDTRIP")
            self.assertFalse(selected["execution_started"])

            result = execute_selected_task(
                {"type": "execute_selected_task", "task_id": "CORE-SEQ-M2-ROUNDTRIP"},
                path,
            )
            self.assertEqual(result["status"], "PASS", result.get("result"))
            self.assertTrue(result["execution_started"])
            self.assertFalse(result["automatic_completion"])

            # Re-read from disk to exercise persistence, not just in-memory state.
            restored = load_queue(path)
            item = next(item for item in restored["items"] if item["id"] == "CORE-SEQ-M2-ROUNDTRIP")
            self.assertEqual(item["status"], "IN_PROGRESS")
            event = restored["history"][-1]
            self.assertEqual(event["event"], "TASK_RESULT_RECORDED")
            self.assertEqual(event["result_status"], "PASS")
            self.assertEqual(len(event["evidence_sha256"]), 64)
            self.assertEqual(event["task_id"], "CORE-SEQ-M2-ROUNDTRIP")

    def test_selected_executor_prepares_real_patch_artifact_without_applying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            source = "autopoesis/task_queue.py"
            expected_test = ROOT / "tests" / "test_task_queue.py"
            existed_before = expected_test.exists()
            update_queue_file(path, [{
                "id": "DISC-PATCH",
                "type": "prepare_test_patch",
                "source": source,
                "evidence": "missing conventional test file",
                "description": "Prepare a test patch.",
            }])
            record_outcome_file(path, "DISC-PATCH", "SELECTED", "selected for bounded patch preparation")
            result = execute_selected_task({"type": "execute_selected_task"}, path)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["task_type"], "prepare_test_patch")
            artifact = result["result"]
            self.assertEqual(artifact["status"], "PATCH_PREPARED")
            self.assertEqual(artifact["files"][0]["path"], "tests/test_task_queue.py")
            self.assertEqual(expected_test.exists(), existed_before)
            item = load_queue(path)["items"][0]
            self.assertEqual(item["status"], "IN_PROGRESS")


    def test_core_011_end_to_end_discovery_selection_verification_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "autopoesis").mkdir()
            (root / "tests").mkdir()
            source = root / "autopoesis" / "candidate.py"
            source.write_text("VALUE = 7\n", encoding="utf-8")
            queue_path = root / "TASK_QUEUE.json"

            discovery = discover_tasks(root)
            self.assertEqual(discovery["status"], "CANDIDATES_FOUND")
            self.assertEqual(discovery["candidate_count"], 1)
            candidate = discovery["candidates"][0]
            self.assertEqual(candidate["type"], "prepare_test_patch")
            self.assertEqual(candidate["source"], "autopoesis/candidate.py")

            merged = update_queue_file(queue_path, discovery["candidates"])
            self.assertEqual(merged["added"], 1)
            selection = select_next_task_file(queue_path)
            self.assertEqual(selection["status"], "TASK_SELECTED")
            self.assertEqual(selection["task_id"], candidate["id"])
            self.assertFalse(selection["execution_started"])

            artifact = prepare_patch_artifact(candidate, root)
            self.assertEqual(validate_patch_artifact(artifact)["status"], "VALID")
            self.assertEqual(artifact["files"][0]["path"], "tests/test_candidate.py")
            verification = verify_test_patch_in_sandbox(candidate, root, timeout_seconds=10)
            self.assertEqual(
                verification["verification_status"],
                "PASS",
                verification.get("stdout", "") + verification.get("stderr", ""),
            )
            self.assertEqual(verification["return_code"], 0)
            self.assertFalse(verification["repository_modified"])
            self.assertFalse((root / "tests" / "test_candidate.py").exists())
            self.assertEqual(source.read_text(encoding="utf-8"), "VALUE = 7\n")

            record_task_result_file(
                queue_path,
                candidate["id"],
                "PASS",
                {"verification_status": verification["verification_status"],
                 "return_code": verification["return_code"],
                 "artifact_sha256": artifact["artifact_sha256"]},
                run_at="2026-10-18T00:00:00+00:00",
                source_sha="b" * 40,
            )
            persisted = load_queue(queue_path)
            item = next(item for item in persisted["items"] if item["id"] == candidate["id"])
            self.assertEqual(item["status"], "SELECTED")
            self.assertEqual(persisted["history"][-1]["event"], "TASK_RESULT_RECORDED")
            self.assertEqual(persisted["history"][-1]["result_status"], "PASS")
            self.assertEqual(len(persisted["history"][-1]["evidence_sha256"]), 64)


    def test_core_012_queue_state_survives_process_restart_and_atomic_writes_leave_no_temp_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue_path = root / "state" / "TASK_QUEUE.json"
            update_queue_file(queue_path, [{
                "id": "CORE-012-PERSIST",
                "type": "proposal",
                "source": "autopoesis/example.py",
                "evidence": "process restart persistence",
                "description": "Confirm state is reloaded from disk by a fresh process.",
            }])
            record_outcome_file(queue_path, "CORE-012-PERSIST", "SELECTED", "persist selection")
            record_task_result_file(
                queue_path,
                "CORE-012-PERSIST",
                "PASS",
                {"verification_status": "PASS", "return_code": 0},
                run_at="2026-10-18T00:00:00+00:00",
                source_sha="c" * 40,
            )

            code = (
                "import json, sys; from pathlib import Path; "
                "from autopoesis.task_queue import load_queue; "
                "q = load_queue(Path(sys.argv[1])); "
                "i = next(x for x in q['items'] if x['id'] == 'CORE-012-PERSIST'); "
                "print(json.dumps({'status': i['status'], 'history': [e['event'] for e in q['history']], "
                "'result': q['history'][-1]['result_status'], 'sha': q['history'][-1]['source_sha']}))"
            )
            completed = subprocess.run(
                [sys.executable, "-c", code, str(queue_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            restored = json.loads(completed.stdout)
            self.assertEqual(restored["status"], "SELECTED")
            self.assertIn("CANDIDATE_ADDED", restored["history"])
            self.assertIn("STATUS_CHANGED", restored["history"])
            self.assertEqual(restored["history"][-1], "TASK_RESULT_RECORDED")
            self.assertEqual(restored["result"], "PASS")
            self.assertEqual(restored["sha"], "c" * 40)
            self.assertEqual(list(queue_path.parent.glob(".TASK_QUEUE.json.*.tmp")), [])


    def test_core_013_failed_atomic_replace_preserves_previous_queue(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            queue_path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(queue_path, [{
                "id": "CORE-013-OLD",
                "type": "proposal",
                "description": "previous durable state",
            }])
            before = queue_path.read_bytes()

            with patch("autopoesis.task_queue.os.replace", side_effect=OSError("simulated replace failure")):
                with self.assertRaisesRegex(OSError, "simulated replace failure"):
                    record_outcome_file(queue_path, "CORE-013-OLD", "SELECTED", "must not partially persist")

            self.assertEqual(queue_path.read_bytes(), before)
            self.assertEqual(load_queue(queue_path)["items"][0]["status"], "OPEN")
            self.assertEqual(list(queue_path.parent.glob(".TASK_QUEUE.json.*.tmp")), [])


    def test_core_014_queue_loader_rejects_malformed_version_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            for malformed in (
                {"version": True, "items": [], "history": []},
                {"version": 1, "items": [], "history": [None]},
                {"version": 1, "items": [], "history": [{"event": ""}]},
            ):
                path.write_text(json.dumps(malformed), encoding="utf-8")
                with self.subTest(malformed=malformed):
                    with self.assertRaises(EvolutionError):
                        load_queue(path)


if __name__ == "__main__":
    unittest.main()
