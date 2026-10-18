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


    def test_decision_journal_round_trip_and_hash_chain(self):
        from autopoesis.receipt_store import append_record, load_journal

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit" / "decisions.json"
            first = append_record(path, {
                "receipt_id": "receipt-1",
                "decision": "ACCEPTED",
                "parent_state_digest": "a" * 64,
                "candidate_state_digest": "b" * 64,
                "evaluator_id": "test-evaluator",
                "evaluator_version": "1",
            })
            second = append_record(path, {
                "receipt_id": "receipt-2",
                "decision": "REJECTED",
                "parent_state_digest": "b" * 64,
                "candidate_state_digest": "c" * 64,
            })
            journal = load_journal(path)
            self.assertEqual(len(journal["entries"]), 2)
            self.assertEqual(first["sequence"], 1)
            self.assertEqual(second["sequence"], 2)
            self.assertEqual(second["previous_digest"], first["entry_digest"])

    def test_decision_journal_detects_tampering(self):
        from autopoesis.receipt_store import JournalIntegrityError, append_record, load_journal

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.json"
            append_record(path, {"receipt_id": "receipt-1", "decision": "ACCEPTED"})
            journal = json.loads(path.read_text(encoding="utf-8"))
            journal["entries"][0]["record"]["decision"] = "REJECTED"
            path.write_text(json.dumps(journal), encoding="utf-8")
            with self.assertRaises(JournalIntegrityError):
                load_journal(path)

    def test_decision_journal_rejects_duplicate_and_malformed_records(self):
        from autopoesis.receipt_store import JournalIntegrityError, append_record

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.json"
            append_record(path, {"receipt_id": "receipt-1", "decision": "ACCEPTED"})
            with self.assertRaises(JournalIntegrityError):
                append_record(path, {"receipt_id": "receipt-1", "decision": "REJECTED"})
            with self.assertRaises(JournalIntegrityError):
                append_record(path, {"decision": "MISSING_ID"})



    def test_decision_journal_is_reachable_through_task_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            queue_path = Path(directory) / "TASK_QUEUE.json"
            result = execute_task(
                {"id": "test-journal", "type": "verify_decision_journal"},
                queue_path,
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["result"]["status"], "CHECKS_PASSED")
        self.assertTrue(result["result"]["tampering_detected"])



    def test_evaluation_receipt_persists_without_semantic_loss(self):
        from run_tasks import verify_evaluation_receipt_persistence

        result = verify_evaluation_receipt_persistence()
        self.assertEqual(result["status"], "CHECKS_PASSED")
        self.assertEqual(result["decision"], "ACCEPTED")
        self.assertTrue(result["persisted_and_reloaded"])
        self.assertTrue(result["fixtures_digest_present"])

    def test_evaluation_receipt_persistence_is_reachable_as_task(self):
        with tempfile.TemporaryDirectory() as directory:
            result = execute_task(
                {"id": "test-evaluation-journal", "type": "verify_evaluation_receipt_persistence"},
                Path(directory) / "TASK_QUEUE.json",
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["result"]["status"], "CHECKS_PASSED")



    def test_typed_evaluation_receipt_rejects_incomplete_receipts(self):
        from autopoesis.receipt_store import JournalIntegrityError, append_evaluation_receipt

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(JournalIntegrityError):
                append_evaluation_receipt(
                    Path(directory) / "decisions.json",
                    {"decision": "ACCEPTED"},
                    receipt_id="incomplete",
                )



    def test_decision_journal_survives_independent_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.json"
            writer = (
                "from autopoesis.receipt_store import append_record; "
                "import sys; "
                "append_record(sys.argv[1], {'receipt_id':'cross-process-1',"
                "'decision':'ACCEPTED','evidence_scope':'test'})"
            )
            writer_result = subprocess.run(
                [sys.executable, "-c", writer, str(path)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(writer_result.returncode, 0, writer_result.stderr)

            reader = (
                "from autopoesis.receipt_store import load_journal; "
                "import json,sys; "
                "print(json.dumps(load_journal(sys.argv[1])['entries'][0]['record']))"
            )
            reader_result = subprocess.run(
                [sys.executable, "-c", reader, str(path)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(reader_result.returncode, 0, reader_result.stderr)
            restored = json.loads(reader_result.stdout)
            self.assertEqual(restored["receipt_id"], "cross-process-1")
            self.assertEqual(restored["decision"], "ACCEPTED")



    def test_execution_policy_fails_closed_without_policy_or_required_controls(self):
        from autopoesis.execution_policy import CandidateExecutionPolicy, assess_execution_policy

        self.assertEqual(assess_execution_policy(None)["status"], "BLOCKED")
        incomplete = CandidateExecutionPolicy(
            command_profile="arbitrary-shell",
            timeout_seconds=0,
            max_output_bytes=0,
            network_disabled=False,
            secrets_excluded=False,
            filesystem_isolated=False,
            os_sandbox_enforced=False,
        )
        result = assess_execution_policy(incomplete)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["execution_performed"])
        self.assertGreaterEqual(len(result["missing_requirements"]), 5)

    def test_complete_execution_policy_declaration_still_grants_no_authority(self):
        from autopoesis.execution_policy import CandidateExecutionPolicy, assess_execution_policy

        policy = CandidateExecutionPolicy(
            command_profile="python-unittest-v1",
            timeout_seconds=30,
            max_output_bytes=100_000,
            network_disabled=True,
            secrets_excluded=True,
            filesystem_isolated=True,
            os_sandbox_enforced=True,
        )
        result = assess_execution_policy(policy)
        self.assertEqual(result["status"], "POLICY_COMPLETE_NOT_AUTHORIZED")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["execution_performed"])
        self.assertIn("do not prove OS isolation", result["reason"])

    def test_execution_boundary_check_is_reachable_through_task_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            result = execute_task(
                {"id": "test-execution-boundary", "type": "verify_candidate_execution_boundary"},
                Path(directory) / "TASK_QUEUE.json",
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["result"]["status"], "CHECKS_PASSED")
        self.assertFalse(result["result"]["execution_performed"])


    def test_host_isolation_inventory_never_claims_verified_sandbox(self):
        from autopoesis.execution_policy import inspect_host_isolation_capabilities

        result = inspect_host_isolation_capabilities()
        self.assertEqual(result["status"], "NO_VERIFIED_SANDBOX")
        self.assertFalse(result["tool_presence_is_proof"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["execution_performed"])
        self.assertIsInstance(result["discovered_tools"], dict)

    def test_host_isolation_inventory_task_is_reachable(self):
        with tempfile.TemporaryDirectory() as directory:
            result = execute_task(
                {"id": "test-host-isolation-inventory", "type": "verify_host_isolation_inventory"},
                Path(directory) / "TASK_QUEUE.json",
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["result"]["status"], "NO_VERIFIED_SANDBOX")
        self.assertFalse(result["result"]["execution_authorized"])


    def test_isolation_runtime_probe_is_diagnostic_only(self):
        from autopoesis.execution_policy import probe_isolation_runtime

        result = probe_isolation_runtime(timeout_seconds=1, output_limit=256)
        self.assertEqual(result["status"], "CAPABILITY_PROBE_ONLY")
        self.assertFalse(result["candidate_code_executed"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["sandbox_verified"])
        self.assertIn("docker_daemon", result["probes"])
        self.assertIn("python_image_cached", result["probes"])
        self.assertIn("podman_runtime", result["probes"])
        self.assertIn("podman_python_image_cached", result["probes"])
        self.assertIn("user_namespace", result["probes"])

    def test_isolation_runtime_probe_rejects_unbounded_parameters(self):
        from autopoesis.execution_policy import probe_isolation_runtime

        with self.assertRaises(ValueError):
            probe_isolation_runtime(timeout_seconds=0)
        with self.assertRaises(ValueError):
            probe_isolation_runtime(output_limit=10)

    def test_isolation_runtime_probe_task_is_reachable(self):
        with tempfile.TemporaryDirectory() as directory:
            result = execute_task(
                {"id": "test-isolation-runtime-probe", "type": "verify_isolation_runtime_probe"},
                Path(directory) / "TASK_QUEUE.json",
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["result"]["status"], "CAPABILITY_PROBE_ONLY")
        self.assertFalse(result["result"]["sandbox_verified"])


    def test_docker_command_builder_is_inert_and_digest_pinned(self):
        from autopoesis.execution_policy import CandidateExecutionPolicy, build_docker_test_command

        policy = CandidateExecutionPolicy(
            command_profile="python-unittest-v1",
            timeout_seconds=30,
            max_output_bytes=100_000,
            network_disabled=True,
            secrets_excluded=True,
            filesystem_isolated=True,
            os_sandbox_enforced=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = build_docker_test_command(
                image_digest="sha256:" + "a" * 64,
                workspace=directory,
                policy=policy,
            )
        argv = result["argv"]
        for flag in ("--network=none", "--read-only", "--cap-drop=ALL",
                     "--security-opt=no-new-privileges:true", "--pids-limit=64",
                     "--memory=256m", "--cpus=1"):
            self.assertIn(flag, argv)
        self.assertEqual(result["status"], "COMMAND_PREPARED_NOT_EXECUTED")
        self.assertFalse(result["shell"])
        self.assertFalse(result["candidate_code_executed"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["sandbox_verified"])
        self.assertIn("python@sha256:" + "a" * 64, argv)

    def test_docker_command_builder_rejects_tags_and_bad_workspace(self):
        from autopoesis.execution_policy import CandidateExecutionPolicy, build_docker_test_command

        policy = CandidateExecutionPolicy(
            command_profile="python-unittest-v1",
            timeout_seconds=30,
            max_output_bytes=100_000,
            network_disabled=True,
            secrets_excluded=True,
            filesystem_isolated=True,
            os_sandbox_enforced=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                build_docker_test_command(image_digest="python:3.12-slim", workspace=directory, policy=policy)
        with self.assertRaises(ValueError):
            build_docker_test_command(image_digest="sha256:" + "a" * 64, workspace="relative/path", policy=policy)

    def test_docker_command_builder_task_is_reachable_and_inert(self):
        with tempfile.TemporaryDirectory() as directory:
            result = execute_task(
                {"id": "test-docker-command-builder", "type": "verify_docker_command_builder"},
                Path(directory) / "TASK_QUEUE.json",
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["result"]["status"], "COMMAND_PREPARED_NOT_EXECUTED")
        self.assertFalse(result["result"]["candidate_code_executed"])
        self.assertFalse(result["result"]["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
