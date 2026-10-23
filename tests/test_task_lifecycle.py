import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import EvolutionError
from autopoesis.task_queue import (
    ALLOWED_TRANSITIONS,
    MAX_ATTEMPTS,
    QUEUE_STATUSES,
    advance_task,
    advance_task_file,
    load_queue,
    merge_candidates,
    empty_queue,
    record_verification_file,
    update_queue_file,
)
from run_tasks import run


SOURCE = "autopoesis/task_queue.py"


def fresh_queue():
    return merge_candidates(empty_queue(), [{"id": "TASK-1", "type": "proposal", "source": SOURCE}])["queue"]


def advance(queue, *statuses):
    for status in statuses:
        queue = advance_task(queue, "TASK-1", status)["queue"]
    return queue


def with_verification(queue, status, source=SOURCE):
    queue = json.loads(json.dumps(queue))
    queue["history"].append({
        "event": "VERIFICATION_RECORDED",
        "task_id": "TASK-1",
        "verification_status": status,
        "verification_level": "UNIT_TEST_FIXTURE",
        "artifact_sha256": None,
        "source": source,
        "at": "2999-01-01T00:00:00+00:00",
    })
    return queue


class TaskLifecycleTests(unittest.TestCase):
    def test_table_covers_every_status_and_terminal_states_have_no_exit(self):
        self.assertEqual(set(ALLOWED_TRANSITIONS), QUEUE_STATUSES)
        for targets in ALLOWED_TRANSITIONS.values():
            self.assertLessEqual(targets, QUEUE_STATUSES)
        self.assertEqual(ALLOWED_TRANSITIONS["DONE"], frozenset())
        self.assertEqual(ALLOWED_TRANSITIONS["REJECTED"], frozenset())

    def test_every_transition_outside_the_table_is_rejected(self):
        paths = {
            "OPEN": (),
            "SELECTED": ("SELECTED",),
            "IN_PROGRESS": ("SELECTED", "IN_PROGRESS"),
            "REJECTED": ("REJECTED",),
        }
        for source, path in paths.items():
            queue = advance(fresh_queue(), *path)
            for target in QUEUE_STATUSES - ALLOWED_TRANSITIONS[source] - {source}:
                with self.subTest(source=source, target=target):
                    with self.assertRaisesRegex(EvolutionError, "Illegal transition"):
                        advance_task(queue, "TASK-1", target)

    def test_done_cannot_be_reopened(self):
        queue = with_verification(advance(fresh_queue(), "SELECTED", "IN_PROGRESS"), "PASS")
        queue = advance(queue, "DONE")
        for target in QUEUE_STATUSES - {"DONE"}:
            with self.assertRaisesRegex(EvolutionError, "Illegal transition"):
                advance_task(queue, "TASK-1", target)

    def test_repeated_transition_is_an_idempotent_no_op(self):
        queue = advance(fresh_queue(), "SELECTED")
        result = advance_task(queue, "TASK-1", "SELECTED")
        self.assertFalse(result["changed"])
        self.assertEqual(result["queue"], queue)

    def test_done_requires_pass_verification_after_latest_attempt(self):
        in_progress = advance(fresh_queue(), "SELECTED", "IN_PROGRESS")
        with self.assertRaisesRegex(EvolutionError, "no PASS verification"):
            advance_task(in_progress, "TASK-1", "DONE")
        with self.assertRaisesRegex(EvolutionError, "no PASS verification"):
            advance_task(with_verification(in_progress, "FAIL"), "TASK-1", "DONE")
        with self.assertRaisesRegex(EvolutionError, "no PASS verification"):
            advance_task(with_verification(with_verification(in_progress, "PASS"), "FAIL"), "TASK-1", "DONE")
        done = advance(with_verification(in_progress, "PASS"), "DONE")
        self.assertEqual(done["items"][0]["status"], "DONE")

    def test_pass_for_a_different_source_does_not_count(self):
        in_progress = advance(fresh_queue(), "SELECTED", "IN_PROGRESS")
        for forged in ("autopoesis/core.py", None):
            queue = with_verification(in_progress, "PASS", source=forged)
            if forged is None:
                del queue["history"][-1]["source"]
            with self.assertRaisesRegex(EvolutionError, "own source"):
                advance_task(queue, "TASK-1", "DONE")

    def test_item_without_source_cannot_reach_done(self):
        queue = merge_candidates(empty_queue(), [{"id": "TASK-1", "type": "proposal"}])["queue"]
        queue = with_verification(advance(queue, "SELECTED", "IN_PROGRESS"), "PASS")
        with self.assertRaisesRegex(EvolutionError, "own source"):
            advance_task(queue, "TASK-1", "DONE")

    def test_verification_file_binds_evidence_to_the_item_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [
                {"id": "TASK-1", "type": "proposal", "source": SOURCE},
                {"id": "NO-SOURCE", "type": "proposal"},
            ])
            before = path.read_bytes()
            for task_id, source, message in (
                ("TASK-1", "autopoesis/core.py", "does not match"),
                ("TASK-1", None, "does not match"),
                ("NO-SOURCE", SOURCE, "no source to bind"),
            ):
                with self.subTest(task_id=task_id, source=source):
                    with self.assertRaisesRegex(EvolutionError, message):
                        record_verification_file(path, task_id, "PASS", "unit", source=source)
            self.assertEqual(path.read_bytes(), before)
            record_verification_file(path, "TASK-1", "PASS", "unit", source=SOURCE)
            self.assertEqual(load_queue(path)["history"][-1]["source"], SOURCE)

    def test_queue_module_exposes_no_unchecked_status_writer(self):
        import autopoesis.task_queue as task_queue
        self.assertFalse(hasattr(task_queue, "record_outcome"))
        self.assertFalse(hasattr(task_queue, "record_outcome_file"))

    def test_pass_from_an_earlier_attempt_does_not_count_after_retry(self):
        queue = with_verification(advance(fresh_queue(), "SELECTED", "IN_PROGRESS"), "PASS")
        queue = advance(queue, "OPEN", "SELECTED", "IN_PROGRESS")
        with self.assertRaisesRegex(EvolutionError, "no PASS verification"):
            advance_task(queue, "TASK-1", "DONE")

    def test_attempt_limit_stops_retries_but_allows_rejection(self):
        queue = fresh_queue()
        for _ in range(MAX_ATTEMPTS):
            queue = advance(queue, "SELECTED", "IN_PROGRESS", "OPEN")
        self.assertEqual(queue["items"][0]["attempts"], MAX_ATTEMPTS)
        queue = advance(queue, "SELECTED")
        with self.assertRaisesRegex(EvolutionError, "attempt limit"):
            advance_task(queue, "TASK-1", "IN_PROGRESS")
        self.assertEqual(advance(queue, "REJECTED")["items"][0]["status"], "REJECTED")

    def test_unknown_task_and_status_are_rejected(self):
        with self.assertRaises(EvolutionError):
            advance_task(fresh_queue(), "MISSING", "SELECTED")
        with self.assertRaises(EvolutionError):
            advance_task(fresh_queue(), "TASK-1", "FINISHED")

    def test_file_no_op_and_rejection_leave_the_file_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [{"id": "TASK-1", "type": "proposal"}])
            advance_task_file(path, "TASK-1", "SELECTED")
            before = path.read_bytes()
            self.assertFalse(advance_task_file(path, "TASK-1", "SELECTED")["changed"])
            with self.assertRaises(EvolutionError):
                advance_task_file(path, "TASK-1", "DONE")
            self.assertEqual(path.read_bytes(), before)

    def test_runner_completes_item_only_through_linked_sandbox_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue_path, tasks_path, results_path = (
                root / "TASK_QUEUE.json", root / "TASKS.json", root / "RESULTS.json"
            )
            update_queue_file(queue_path, [
                {"id": "QUEUE-ITEM", "type": "proposal", "source": SOURCE},
                {"id": "OTHER-ITEM", "type": "proposal", "source": "autopoesis/core.py"},
            ])

            def run_tasks(*tasks):
                tasks_path.write_text(json.dumps({"tasks": list(tasks)}), encoding="utf-8")
                code = run(tasks_path, results_path, queue_path)
                return code, json.loads(results_path.read_text(encoding="utf-8"))

            def status(target, task_id="set"):
                return {"id": task_id, "type": "update_task_status", "task_id": "QUEUE-ITEM", "status": target}

            code, results = run_tasks(status("SELECTED", "s"), status("IN_PROGRESS", "p"), status("DONE", "d"))
            self.assertEqual(code, 1)
            self.assertIn("no PASS verification", results["tasks"][2]["error"])

            # A real PASS for task_queue.py must not be credited to an item about core.py.
            code, results = run_tasks({
                "id": "verify-other",
                "type": "verify_test_patch_sandbox",
                "source": SOURCE,
                "queue_task_id": "OTHER-ITEM",
            })
            self.assertEqual(code, 1)
            self.assertIn("does not match", results["tasks"][0]["error"])
            self.assertFalse([e for e in load_queue(queue_path)["history"] if e["event"] == "VERIFICATION_RECORDED"])

            code, _ = run_tasks({
                "id": "verify",
                "type": "verify_test_patch_sandbox",
                "source": "autopoesis/task_queue.py",
                "queue_task_id": "QUEUE-ITEM",
            }, status("DONE"))
            self.assertEqual(code, 0)
            queue = load_queue(queue_path)
            item = next(i for i in queue["items"] if i["id"] == "QUEUE-ITEM")
            self.assertEqual(item["status"], "DONE")
            self.assertEqual(item["attempts"], 1)
            evidence = [e for e in queue["history"] if e["event"] == "VERIFICATION_RECORDED"]
            self.assertEqual([e["task_id"] for e in evidence], ["QUEUE-ITEM"])

            code, results = run_tasks(status("OPEN"))
            self.assertEqual(code, 1)
            self.assertIn("Illegal transition", results["tasks"][0]["error"])
            item = next(i for i in load_queue(queue_path)["items"] if i["id"] == "QUEUE-ITEM")
            self.assertEqual(item["status"], "DONE")


ROOT = Path(__file__).resolve().parents[1]


def workflow_seed_script():
    """Return the Python body of the CI seed probe step, exactly as the workflow runs it."""
    lines = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8").splitlines()
    start = lines.index("      - name: Seed synthetic DONE probe for cross-run verification")
    begin = next(i for i in range(start, len(lines)) if lines[i].strip() == "python - <<'PY'")
    end = next(i for i in range(begin + 1, len(lines)) if lines[i].strip() == "PY")
    return "\n".join(line[10:] for line in lines[begin + 1:end]) + "\n"


class WorkflowSeedProbeTests(unittest.TestCase):
    def test_seed_probe_uses_only_the_governed_lifecycle(self):
        script = workflow_seed_script()
        self.assertNotIn("record_outcome", script)
        self.assertIn("advance_task_file", script)

    def test_seed_probe_reaches_done_through_verified_transitions(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "PYTHONPATH": str(ROOT)}
            completed = subprocess.run(
                [sys.executable, "-c", workflow_seed_script()],
                cwd=directory, env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            queue = load_queue(Path(directory) / "TASK_QUEUE.json")
        probe = next(item for item in queue["items"] if item["id"] == "CI-RESTORE-DONE-PROBE")
        self.assertEqual(probe["status"], "DONE")
        self.assertEqual(probe["attempts"], 1)
        steps = [
            (event["event"], event.get("to") or event.get("verification_status"))
            for event in queue["history"] if event["task_id"] == "CI-RESTORE-DONE-PROBE"
        ]
        self.assertEqual(steps, [
            ("CANDIDATE_ADDED", None),
            ("STATUS_CHANGED", "SELECTED"),
            ("STATUS_CHANGED", "IN_PROGRESS"),
            ("VERIFICATION_RECORDED", "PASS"),
            ("STATUS_CHANGED", "DONE"),
        ])
        self.assertTrue(any(
            event.get("task_id") == "CI-RESTORE-VERIFICATION-PROBE" for event in queue["history"]
        ))


if __name__ == "__main__":
    unittest.main()
