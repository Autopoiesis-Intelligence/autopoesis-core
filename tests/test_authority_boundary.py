# Agent: Claude
"""T2C-006 on today's code: a validated candidate cannot reach protected files, and a PASS is not completion."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import canonical_json
from autopoesis.executor import apply_patch_to_sandbox, validate_patch_artifact
from autopoesis.task_queue import load_queue, record_verification_file, update_queue_file

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_TARGETS = (
    "autopoesis/core.py",
    "run_tasks.py",
    "AGENTS.md",
    ".github/workflows/ci.yml",
    "docs/theory/CLAIMS.md",
    "tests/../autopoesis/core.py",
    "tests/nested/test_escape.py",
)


def artifact_for(path, content="VALUE = 1\n"):
    artifact = {
        "status": "PATCH_PREPARED",
        "writer_id": "authority-boundary-test",
        "task_id": "T2C-006",
        "files": [{"path": path, "content": content, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}],
        "rationale": "candidate that claims to be selected and verified",
    }
    artifact["artifact_sha256"] = hashlib.sha256(canonical_json(artifact).encode("utf-8")).hexdigest()
    return artifact


def tree_digest(root):
    """Digest of every file under root except git metadata and bytecode caches."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_dir() or relative.parts[0] == ".git" or "__pycache__" in relative.parts:
            continue
        digest.update(relative.as_posix().encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


class AuthorityBoundaryTest(unittest.TestCase):
    def test_candidate_targeting_protected_files_is_refused_and_nothing_changes(self):
        before = tree_digest(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            for target in PROTECTED_TARGETS:
                with self.subTest(target=target):
                    with self.assertRaises(ValueError):
                        validate_patch_artifact(artifact_for(target))
                    with self.assertRaises(ValueError):
                        apply_patch_to_sandbox(artifact_for(target), sandbox)
            self.assertEqual([], list(sandbox.rglob("*")))
        self.assertEqual(before, tree_digest(ROOT))

    def test_pass_is_recorded_as_evidence_without_completing_the_task(self):
        with tempfile.TemporaryDirectory() as directory:
            queue_path = Path(directory) / "TASK_QUEUE.json"
            update_queue_file(queue_path, [{"id": "T1", "source": "autopoesis/core.py", "kind": "MISSING_TEST", "reason": "probe"}])
            before = load_queue(queue_path)

            record_verification_file(queue_path, "T1", "PASS", "GENERATED_TEST_EXECUTION", "a" * 64)

            after = load_queue(queue_path)
            self.assertEqual(before["items"], after["items"])
            self.assertEqual(["OPEN"], [item["status"] for item in after["items"]])
            new_events = after["history"][len(before["history"]):]
            self.assertEqual(["VERIFICATION_RECORDED"], [event["event"] for event in new_events])


if __name__ == "__main__":
    unittest.main()
