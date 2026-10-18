"""Validation tests for persisted task queue history."""

import json
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import EvolutionError
from autopoesis.task_queue import load_queue, update_queue_file, record_outcome_file


class QueueHistoryValidationTests(unittest.TestCase):
    def _write_queue(self, history):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "TASK_QUEUE.json"
        path.write_text(json.dumps({
            "version": 1,
            "items": [{"id": "TASK-1", "status": "DONE"}],
            "history": history,
        }), encoding="utf-8")
        return path

    def test_rejects_non_object_history_entry(self):
        with self.assertRaisesRegex(EvolutionError, "expected an object"):
            load_queue(self._write_queue(["not-an-event"]))

    def test_rejects_non_string_history_event_type(self):
        with self.assertRaisesRegex(EvolutionError, "unsupported event type"):
            load_queue(self._write_queue([{
                "event": ["UNKNOWN"],
                "task_id": "TASK-1",
                "at": "2026-01-01T00:00:00+00:00",
            }]))

    def test_rejects_unknown_history_event_type(self):
        with self.assertRaisesRegex(EvolutionError, "unsupported event type"):
            load_queue(self._write_queue([{
                "event": "UNKNOWN",
                "task_id": "TASK-1",
                "at": "2026-01-01T00:00:00+00:00",
            }]))

    def test_rejects_missing_task_id_or_timestamp(self):
        with self.assertRaisesRegex(EvolutionError, "task_id"):
            load_queue(self._write_queue([{
                "event": "CANDIDATE_ADDED",
                "at": "2026-01-01T00:00:00+00:00",
            }]))
        with self.assertRaisesRegex(EvolutionError, "at"):
            load_queue(self._write_queue([{
                "event": "CANDIDATE_ADDED",
                "task_id": "TASK-1",
                "at": "",
            }]))

    def test_rejects_non_string_queue_status(self):
        # The task status is independently validated before history records.
        path = self._write_queue([])
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["items"][0]["status"] = ["DONE"]
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(EvolutionError, "Invalid status"):
            load_queue(path)

    def test_rejects_invalid_status_transition_history(self):
        with self.assertRaisesRegex(EvolutionError, "destination status"):
            load_queue(self._write_queue([{
                "event": "STATUS_CHANGED",
                "task_id": "TASK-1",
                "from": "OPEN",
                "to": "UNKNOWN",
                "note": "bad status",
                "at": "2026-01-01T00:00:00+00:00",
            }]))

    def test_rejects_non_string_transition_note(self):
        with self.assertRaisesRegex(EvolutionError, "note must be a string"):
            load_queue(self._write_queue([{
                "event": "STATUS_CHANGED",
                "task_id": "TASK-1",
                "from": "OPEN",
                "to": "DONE",
                "note": ["not-a-string"],
                "at": "2026-01-01T00:00:00+00:00",
            }]))

    def test_accepts_history_written_by_queue_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(path, [{
                "id": "TASK-1",
                "type": "proposal",
                "description": "test",
            }])
            record_outcome_file(path, "TASK-1", "DONE", "test transition")
            queue = load_queue(path)
            self.assertEqual([event["event"] for event in queue["history"]], [
                "CANDIDATE_ADDED",
                "STATUS_CHANGED",
            ])


if __name__ == "__main__":
    unittest.main()
